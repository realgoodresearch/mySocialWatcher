from __future__ import annotations

import os
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
    create_engine,
    literal,
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

    def write(self, token: str, collection: str, rows: Sequence[NormalizedRow]) -> tuple[int, int]:
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

                grouped: dict[str, list[dict]] = defaultdict(list)
                for row in rows:
                    values = row.model_dump(exclude={"source_index", "table"})
                    values.update(collection_id=collection_id, contributor_id=contributor_id)
                    grouped[row.table].append(values)

                inserted = 0
                for table_name, values in grouped.items():
                    result = connection.execute(
                        insert(AUDIENCE_TABLES[table_name])
                        .values(values)
                        .on_conflict_do_nothing()
                        .returning(literal(1))
                    )
                    inserted += len(result.all())
                return inserted, len(rows) - inserted
        except AuthenticationError:
            raise
        except (OperationalError, SQLAlchemyError) as exc:
            raise DatabaseWriteError("database batch write failed") from exc
