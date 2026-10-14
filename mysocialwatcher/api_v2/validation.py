from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class RowInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_index: int = Field(ge=0)
    platform: Literal["facebook", "instagram"]
    timestamp: int
    geo_locations: dict[str, Any]
    gender: Literal[0, 1, 2]
    age_min: int
    age_max: int = 999
    dau: int
    mau: int | None = None
    mau_lower: int | None = None
    mau_upper: int | None = None
    valid: bool = False
    country: str | None = None
    all_fields: dict[str, Any] = Field(default_factory=dict)
    targeting: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] | list[dict[str, Any]]

    @model_validator(mode="after")
    def audience_estimate_present(self) -> "RowInput":
        if self.mau is None and self.mau_lower is None and self.mau_upper is None:
            raise ValueError("at least one of mau, mau_lower, or mau_upper is required")
        return self


class NormalizedRow(BaseModel):
    source_index: int
    table: Literal["facebook", "facebook_invalid", "instagram", "instagram_invalid"]
    collection_date: date
    country: str
    gender: int
    age_min: int
    age_max: int
    dau: int
    mau: int | None
    mau_lower: int | None
    mau_upper: int | None
    timestamp: int
    geo_locations: dict[str, Any]
    all_fields: dict[str, Any]
    targeting: dict[str, Any]
    response: dict[str, Any] | list[dict[str, Any]]


def countries_from_geo_locations(geo: dict[str, Any]) -> set[str]:
    countries: set[str] = set()
    if geo.get("name") == "countries":
        countries.update(value for value in geo.get("values", []) if isinstance(value, str))
    else:
        reference = geo.get("pySocialWatcherReference")
        if isinstance(reference, str):
            for component in reference.split("; "):
                key, separator, value = component.partition(":")
                if separator and key in {"country", "country_code"}:
                    countries.add(value)
        elif isinstance(reference, dict):
            for key in ("country", "country_code"):
                if isinstance(reference.get(key), str):
                    countries.add(reference[key])

        for value in geo.get("values", []):
            if not isinstance(value, dict):
                continue
            for key, candidate in value.items():
                if "country" in key and isinstance(candidate, str) and len(candidate) == 2:
                    countries.add(candidate)

        for key, candidate in geo.items():
            if "country" in key and isinstance(candidate, str) and len(candidate) == 2:
                countries.add(candidate)

    return {country.upper() for country in countries if len(country) == 2}


def estimate_ready(response: dict[str, Any] | list[dict[str, Any]]) -> bool:
    items = [response] if isinstance(response, dict) else response
    if not items:
        raise ValueError('could not verify "estimate ready" from response')
    try:
        return all(bool(item["data"][0]["estimate_ready"]) for item in items)
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError('could not verify "estimate ready" from response') from exc


def normalize_row(raw: dict[str, Any]) -> NormalizedRow:
    row = RowInput.model_validate(raw)
    countries = countries_from_geo_locations(row.geo_locations)
    if not countries:
        raise ValueError("iso-2 country code could not be determined from geo_locations")
    if len(countries) > 1:
        raise ValueError("more than one iso-2 country code identified from geo_locations")
    country = next(iter(countries))
    if country == "XX":
        raise ValueError("XX is not a valid country code")

    valid = row.valid and estimate_ready(row.response)
    table = row.platform if valid else f"{row.platform}_invalid"
    collection_date = datetime.fromtimestamp(row.timestamp, tz=timezone.utc).date().isoformat()

    return NormalizedRow(
        source_index=row.source_index,
        table=table,
        collection_date=collection_date,
        country=country,
        gender=row.gender,
        age_min=row.age_min,
        age_max=row.age_max,
        dau=row.dau,
        mau=row.mau,
        mau_lower=row.mau_lower,
        mau_upper=row.mau_upper,
        timestamp=row.timestamp,
        geo_locations=row.geo_locations,
        all_fields=row.all_fields,
        targeting=row.targeting,
        response=row.response,
    )


def validation_message(exc: ValidationError | ValueError) -> str:
    if isinstance(exc, ValidationError):
        error = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in error["loc"])
        return f"{location}: {error['msg']}" if location else error["msg"]
    return str(exc)
