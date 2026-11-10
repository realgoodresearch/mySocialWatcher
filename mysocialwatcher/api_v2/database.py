from __future__ import annotations

import os
import json
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    cast,
    create_engine,
    false,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from mysocialwatcher.api_v2.validation import NormalizedRow


class AuthenticationError(Exception):
    pass


class DatabaseWriteError(Exception):
    pass


metadata = MetaData()
collections = Table(
    "collections",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(50), nullable=False, unique=True),
)
tokens = Table(
    "tokens",
    metadata,
    Column("contributor_id", Integer, nullable=False),
    Column("token", String(50), nullable=False, unique=True),
    Column("write", Boolean, nullable=False),
)


def audience_table(name: str) -> Table:
    return Table(
        name,
        metadata,
        Column("collection_id", Integer),
        Column("contributor_id", Integer),
        Column("collection_date", Date, nullable=False),
        Column("country", String(2), nullable=False),
        Column("gender", SmallInteger, nullable=False),
        Column("age_min", SmallInteger, nullable=False),
        Column("age_max", SmallInteger, nullable=False),
        Column("dau", Integer, nullable=False),
        Column("mau", Integer),
        Column("mau_lower", Integer),
        Column("mau_upper", Integer),
        Column("timestamp", BigInteger, nullable=False),
        Column("geo_locations", JSONB, nullable=False),
        Column("all_fields", JSONB),
        Column("targeting", JSONB),
        Column("response", JSONB),
    )


AUDIENCE_TABLES = {
    name: audience_table(name)
    for name in ("facebook", "facebook_invalid", "instagram", "instagram_invalid")
}


def engine_from_environment() -> Engine:
    url = os.environ.get("SOCIALWATCHER_V2_DATABASE_URL")
    if not url:
        settings = {
            "username": "writer",
            "password": os.environ.get("POSTGRES_WPASS"),
            "host": os.environ.get("POSTGRES_HOST"),
            "port": os.environ.get("POSTGRES_PORT"),
            "database": os.environ.get("POSTGRES_DB"),
        }
        missing = [key for key, value in settings.items() if value is None]
        if missing:
            raise RuntimeError(
                "SOCIALWATCHER_V2_DATABASE_URL or PostgreSQL settings are required; "
                f"missing: {', '.join(missing)}"
            )
        url = URL.create("postgresql+psycopg", **settings)
    return create_engine(
        url,
        pool_size=3,
        max_overflow=0,
        pool_pre_ping=True,
        pool_timeout=30,
        connect_args={"connect_timeout": 10},
    )


class BatchWriter:
    def __init__(self, engine: Engine):
        self.engine = engine

    def write(self, token: str, collection: str,
              rows: Sequence[NormalizedRow]) -> dict[int, str]:
        try:
            with self.engine.begin() as connection:
                contributor_id = connection.execute(
                    select(tokens.c.contributor_id).where(
                        tokens.c.token == token, tokens.c.write.is_(True)
                    )
                ).scalar_one_or_none()
                if contributor_id is None:
                    raise AuthenticationError("token is not authorized for writes")

                collection = collection.strip("_")
                collection_id = connection.execute(
                    select(collections.c.id).where(collections.c.name == collection)
                ).scalar_one_or_none()
                if collection_id is None:
                    collection_id = connection.execute(
                        insert(collections)
                        .values(name=collection)
                        .on_conflict_do_nothing(index_elements=[collections.c.name])
                        .returning(collections.c.id)
                    ).scalar_one_or_none()
                    if collection_id is None:
                        collection_id = connection.execute(
                            select(collections.c.id).where(collections.c.name == collection)
                        ).scalar_one()

                grouped: dict[str, list[tuple[NormalizedRow, dict]]] = defaultdict(list)
                for row in rows:
                    values = row.model_dump(exclude={"source_index", "table"})
                    values.update(collection_id=collection_id, contributor_id=contributor_id)
                    grouped[row.table].append((row, values))

                actions: dict[int, str] = {}
                identity_columns = (
                    "country", "collection_date", "gender", "age_min", "age_max", "dau",
                    "geo_locations", "targeting", "response",
                )
                for table_name, items in grouped.items():
                    table = AUDIENCE_TABLES[table_name]
                    selected: dict[tuple, tuple[NormalizedRow, dict]] = {}
                    for row, values in items:
                        identity = _row_identity(values)
                        current = selected.get(identity)
                        if current is None or (_is_refined(values) and not _is_refined(current[1])):
                            selected[identity] = (row, values)
                    source_by_identity = {
                        identity: row.source_index
                        for identity, (row, _) in selected.items()
                    }
                    index_elements = [
                        table.c.country, table.c.collection_date, table.c.gender,
                        table.c.age_min, table.c.age_max, table.c.dau,
                        func.md5(cast(table.c.geo_locations, Text)),
                        func.md5(cast(table.c.targeting, Text)),
                        func.md5(cast(table.c.response, Text)),
                    ]
                    statement = insert(table).values(
                        [values for _, values in selected.values()]
                    )
                    inserted = connection.execute(
                        statement.on_conflict_do_nothing(index_elements=index_elements)
                        .returning(*(table.c[name] for name in identity_columns))
                    )
                    inserted_identities = set()
                    for written in inserted.mappings():
                        identity = _row_identity(written)
                        inserted_identities.add(identity)
                        actions[source_by_identity[identity]] = "inserted"

                    promotion_values = [
                        values for identity, (_, values) in selected.items()
                        if identity not in inserted_identities and _is_refined(values)
                    ]
                    if not promotion_values:
                        continue
                    statement = insert(table).values(promotion_values)
                    refinement_marker = {"better_estimates": True}
                    promoted = connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=index_elements,
                            set_={
                                "mau": statement.excluded.mau,
                                "mau_lower": statement.excluded.mau_lower,
                                "mau_upper": statement.excluded.mau_upper,
                                "all_fields": statement.excluded.all_fields,
                            },
                            where=(
                                statement.excluded.all_fields.contains(refinement_marker)
                                & ~func.coalesce(
                                    table.c.all_fields.contains(refinement_marker), false()
                                )
                            ),
                        )
                        .returning(*(table.c[name] for name in identity_columns))
                    )
                    for written in promoted.mappings():
                        actions[source_by_identity[_row_identity(written)]] = "promoted"
                return actions
        except AuthenticationError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise DatabaseWriteError("database batch write failed") from exc


def _row_identity(values) -> tuple:
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    return (
        values["country"], values["collection_date"], values["gender"],
        values["age_min"], values["age_max"], values["dau"],
        canonical(values["geo_locations"]), canonical(values.get("targeting") or {}),
        canonical(values["response"]),
    )


def _is_refined(values) -> bool:
    return values.get("all_fields", {}).get("better_estimates") is True
