from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen


GEONAMES_DUMP_BASE_URL = "https://download.geonames.org/export/dump"
HTTP_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class AfricanCountry:
    country: str
    iso2: str


AFRICAN_COUNTRIES: tuple[AfricanCountry, ...] = (
    AfricanCountry("Algeria", "DZ"),
    AfricanCountry("Angola", "AO"),
    AfricanCountry("Benin", "BJ"),
    AfricanCountry("Botswana", "BW"),
    AfricanCountry("Burkina Faso", "BF"),
    AfricanCountry("Burundi", "BI"),
    AfricanCountry("Cabo Verde", "CV"),
    AfricanCountry("Cameroon", "CM"),
    AfricanCountry("Central African Republic", "CF"),
    AfricanCountry("Chad", "TD"),
    AfricanCountry("Comoros", "KM"),
    AfricanCountry("Congo", "CG"),
    AfricanCountry("Cote d'Ivoire", "CI"),
    AfricanCountry("Democratic Republic of the Congo", "CD"),
    AfricanCountry("Djibouti", "DJ"),
    AfricanCountry("Egypt", "EG"),
    AfricanCountry("Equatorial Guinea", "GQ"),
    AfricanCountry("Eritrea", "ER"),
    AfricanCountry("Eswatini", "SZ"),
    AfricanCountry("Ethiopia", "ET"),
    AfricanCountry("Gabon", "GA"),
    AfricanCountry("Gambia", "GM"),
    AfricanCountry("Ghana", "GH"),
    AfricanCountry("Guinea", "GN"),
    AfricanCountry("Guinea-Bissau", "GW"),
    AfricanCountry("Kenya", "KE"),
    AfricanCountry("Lesotho", "LS"),
    AfricanCountry("Liberia", "LR"),
    AfricanCountry("Libya", "LY"),
    AfricanCountry("Madagascar", "MG"),
    AfricanCountry("Malawi", "MW"),
    AfricanCountry("Mali", "ML"),
    AfricanCountry("Mauritania", "MR"),
    AfricanCountry("Mauritius", "MU"),
    AfricanCountry("Morocco", "MA"),
    AfricanCountry("Mozambique", "MZ"),
    AfricanCountry("Namibia", "NA"),
    AfricanCountry("Niger", "NE"),
    AfricanCountry("Nigeria", "NG"),
    AfricanCountry("Rwanda", "RW"),
    AfricanCountry("Sao Tome and Principe", "ST"),
    AfricanCountry("Senegal", "SN"),
    AfricanCountry("Seychelles", "SC"),
    AfricanCountry("Sierra Leone", "SL"),
    AfricanCountry("Somalia", "SO"),
    AfricanCountry("South Africa", "ZA"),
    AfricanCountry("South Sudan", "SS"),
    AfricanCountry("Sudan", "SD"),
    AfricanCountry("Tanzania", "TZ"),
    AfricanCountry("Togo", "TG"),
    AfricanCountry("Tunisia", "TN"),
    AfricanCountry("Uganda", "UG"),
    AfricanCountry("Western Sahara", "EH"),
    AfricanCountry("Zambia", "ZM"),
    AfricanCountry("Zimbabwe", "ZW"),
)


AFRICAN_COUNTRY_BY_CODE = {item.iso2: item for item in AFRICAN_COUNTRIES}
AFRICAN_COUNTRY_BY_NAME = {item.country.upper(): item for item in AFRICAN_COUNTRIES}


def default_cache_dir() -> Path:
    return Path(__file__).resolve().parents[1] / ".cache" / "geonames"


def list_african_countries() -> list[dict[str, str]]:
    return [
        {
            "country": item.country,
            "iso2": item.iso2,
        }
        for item in AFRICAN_COUNTRIES
    ]


def resolve_african_country(value: str) -> AfricanCountry:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("A country selection is required.")
    if len(normalized) == 2:
        country = AFRICAN_COUNTRY_BY_CODE.get(normalized.upper())
        if country:
            return country
    country = AFRICAN_COUNTRY_BY_NAME.get(normalized.upper())
    if country:
        return country
    available = ", ".join(item.country for item in AFRICAN_COUNTRIES)
    raise ValueError(
        f"Unsupported African country '{value}'. Supported countries: {available}."
    )


def geonames_dump_url(iso2: str) -> str:
    return f"{GEONAMES_DUMP_BASE_URL}/{iso2.upper()}.zip"


def geonames_cache_paths(country: AfricanCountry, cache_dir: Path | None = None) -> tuple[Path, Path]:
    base_dir = cache_dir or default_cache_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    return (
        base_dir / f"{country.iso2.upper()}.zip",
        base_dir / f"{country.iso2.upper()}_localities.json",
    )


def download_geonames_country_dump(country: AfricanCountry, cache_dir: Path | None = None) -> Path:
    zip_path, _ = geonames_cache_paths(country, cache_dir=cache_dir)
    if zip_path.exists():
        return zip_path
    request = Request(
        geonames_dump_url(country.iso2),
        headers={"User-Agent": "Mictlan-AgriXGBoost locality loader"},
    )
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        temp_path = zip_path.with_suffix(f"{zip_path.suffix}.tmp")
        temp_path.write_bytes(response.read())
        temp_path.replace(zip_path)
    return zip_path


def parse_geonames_localities(zip_path: Path, country: AfricanCountry) -> list[dict[str, object]]:
    with zipfile.ZipFile(zip_path) as archive:
        member_name = f"{country.iso2.upper()}.txt"
        if member_name not in archive.namelist():
            raise FileNotFoundError(
                f"The GeoNames dump for {country.country} does not contain {member_name}."
            )
        with archive.open(member_name) as raw_handle:
            text_stream = io.TextIOWrapper(raw_handle, encoding="utf-8")
            reader = csv.reader(text_stream, delimiter="\t")
            localities: list[dict[str, object]] = []
            seen: set[tuple[str, str, str]] = set()
            for row in reader:
                if len(row) < 15:
                    continue
                feature_class = row[6].strip()
                if feature_class != "P":
                    continue
                geoname_id = row[0].strip()
                name = row[1].strip()
                latitude = row[4].strip()
                longitude = row[5].strip()
                feature_code = row[7].strip()
                population_text = row[14].strip()
                if not geoname_id or not name or not latitude or not longitude:
                    continue
                dedupe_key = (name, latitude, longitude)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                try:
                    population = int(population_text or "0")
                except ValueError:
                    population = 0
                localities.append(
                    {
                        "geoname_id": geoname_id,
                        "name": name,
                        "latitude": latitude,
                        "longitude": longitude,
                        "feature_code": feature_code,
                        "population": population,
                        "country": country.country,
                        "country_code": country.iso2,
                    }
                )
    localities.sort(key=lambda item: (-int(item["population"]), str(item["name"])))
    return localities


def load_country_localities(country_value: str, cache_dir: Path | None = None) -> list[dict[str, object]]:
    country = resolve_african_country(country_value)
    zip_path, json_path = geonames_cache_paths(country, cache_dir=cache_dir)
    if json_path.exists():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            json_path.unlink(missing_ok=True)

    for attempt in range(2):
        try:
            download_geonames_country_dump(country, cache_dir=cache_dir)
            localities = parse_geonames_localities(zip_path, country)
            json_path.write_text(json.dumps(localities, ensure_ascii=False), encoding="utf-8")
            return localities
        except (EOFError, OSError, zipfile.BadZipFile):
            zip_path.unlink(missing_ok=True)
            if attempt == 1:
                raise

    raise RuntimeError(f"Unable to load GeoNames localities for {country.country}.")


def sample_country_localities(
    country_value: str,
    *,
    cache_dir: Path | None = None,
    limit: int = 5,
) -> dict[str, object]:
    country = resolve_african_country(country_value)
    localities = load_country_localities(country.iso2, cache_dir=cache_dir)
    return {
        "country": country.country,
        "iso2": country.iso2,
        "locality_count": len(localities),
        "sample": localities[: max(limit, 0)],
    }


def normalize_bounds(
    latitude_min: float,
    latitude_max: float,
    longitude_min: float,
    longitude_max: float,
) -> tuple[float, float, float, float]:
    return (
        min(latitude_min, latitude_max),
        max(latitude_min, latitude_max),
        min(longitude_min, longitude_max),
        max(longitude_min, longitude_max),
    )


def filter_localities_within_bounds(
    latitude_min: float,
    latitude_max: float,
    longitude_min: float,
    longitude_max: float,
    *,
    cache_dir: Path | None = None,
) -> list[dict[str, object]]:
    latitude_min, latitude_max, longitude_min, longitude_max = normalize_bounds(
        latitude_min,
        latitude_max,
        longitude_min,
        longitude_max,
    )
    filtered: list[dict[str, object]] = []
    for country in AFRICAN_COUNTRIES:
        for locality in load_country_localities(country.iso2, cache_dir=cache_dir):
            try:
                latitude = float(locality["latitude"])
                longitude = float(locality["longitude"])
            except (TypeError, ValueError, KeyError):
                continue
            if latitude_min <= latitude <= latitude_max and longitude_min <= longitude <= longitude_max:
                filtered.append(locality)
    filtered.sort(key=lambda item: (-int(item.get("population", 0) or 0), str(item.get("name", ""))))
    return filtered


def sample_localities_within_bounds(
    latitude_min: float,
    latitude_max: float,
    longitude_min: float,
    longitude_max: float,
    *,
    cache_dir: Path | None = None,
    limit: int = 5,
) -> dict[str, object]:
    latitude_min, latitude_max, longitude_min, longitude_max = normalize_bounds(
        latitude_min,
        latitude_max,
        longitude_min,
        longitude_max,
    )
    localities = filter_localities_within_bounds(
        latitude_min,
        latitude_max,
        longitude_min,
        longitude_max,
        cache_dir=cache_dir,
    )
    return {
        "latitude_min": latitude_min,
        "latitude_max": latitude_max,
        "longitude_min": longitude_min,
        "longitude_max": longitude_max,
        "locality_count": len(localities),
        "sample": localities[: max(limit, 0)],
    }
