from __future__ import annotations

import json
from datetime import time
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
VIS_DIR = ROOT / "visualization"

JAZDY_INPUT = ROOT / "data" / "clean" / "dataset_jazdy_2024_cleaned.xlsx"
MATERIAL_INPUT = ROOT / "data" / "raw" / "dataset_material_2023_2025.xlsx"
HTML_OUTPUT = VIS_DIR / "analyza_dashboard.html"

MONTH_NAMES_SK = {
    1: "januar",
    2: "februar",
    3: "marec",
    4: "april",
    5: "maj",
    6: "jun",
    7: "jul",
    8: "august",
    9: "september",
    10: "oktober",
    11: "november",
    12: "december",
}

WEEKDAY_NAMES_SK = {
    0: "Po",
    1: "Ut",
    2: "St",
    3: "Stv",
    4: "Pi",
    5: "So",
    6: "Ne",
}

JAZDY_FIELDS = [
    {
        "name": "DATUM",
        "description": "Datum jazdy po zjednoteni formatov na konzistentny kalendarny den.",
        "type": "DATE",
    },
    {
        "name": "SPZ",
        "description": "Anonymizovany identifikator vozidla. V datasete je 18 unikatnych vozidiel.",
        "type": "STRING",
    },
    {
        "name": "CAS_OD / CAS_DO",
        "description": "Cas zaciatku a konca zaznamu. Umoznuje odhad trvania jazdy.",
        "type": "TIME",
    },
    {
        "name": "DOBA_STATIA_MIN",
        "description": "Dlzka statia medzi jazdami. Je vhodna na hladanie neefektivnych zaznamov.",
        "type": "DECIMAL",
    },
    {
        "name": "EW_* / EL_*",
        "description": "Start a koniec polohy. Sluzia len na odhad priamej vzdialenosti, nie realnej trasy.",
        "type": "COORD",
    },
    {
        "name": "DIST_START_END_M",
        "description": "Priama vzdialenost medzi startom a cielom po vycisteni dat.",
        "type": "NUMERIC",
    },
    {
        "name": "FLAGY",
        "description": "Odvodene priznaky near-zero, short-trip a potentially-inefficient pre rychlu segmentaciu.",
        "type": "BOOLEAN",
    },
]

MATERIAL_FIELDS = [
    {
        "name": "DATUM",
        "description": "Datum pohybu materialu po znormalizovani casovej osi na roky 2023 az 2025.",
        "type": "DATE",
    },
    {
        "name": "MAT_NR",
        "description": "Kod materialu. Prefix prvych 8 znakov sa pouziva ako jednoducha skupina.",
        "type": "STRING",
    },
    {
        "name": "MNOZSTVO",
        "description": "Ocistene numericke mnozstvo pohybu bez dalsieho rozlisenia smeru pohybu.",
        "type": "DECIMAL",
    },
    {
        "name": "ABC_SEGMENT",
        "description": "Odvodena ABC segmentacia podla kumulativneho podielu na celkovom mnozstve.",
        "type": "CATEGORY",
    },
]


def parse_mixed_date(value: object, formats: list[str]) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        return value

    text = str(value).strip()
    for fmt in formats:
        try:
            return pd.to_datetime(text, format=fmt)
        except (TypeError, ValueError):
            continue

    return pd.to_datetime(text, errors="coerce", dayfirst=True)


def format_time(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, pd.Timestamp):
        return value.strftime("%H:%M:%S")

    text = str(value).strip()
    try:
        parsed = pd.to_datetime(text, format="%H:%M:%S")
        return parsed.strftime("%H:%M:%S")
    except (TypeError, ValueError):
        return text


def parse_time_to_seconds(value: object) -> float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, time):
        return float(value.hour * 3600 + value.minute * 60 + value.second)
    if isinstance(value, pd.Timestamp):
        return float(value.hour * 3600 + value.minute * 60 + value.second)

    parts = str(value).strip().split(":")
    if len(parts) != 3:
        return np.nan

    try:
        return float(int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2]))
    except ValueError:
        return np.nan


def parse_decimal_or_scaled(value: object, scaled_divisor: float = 1e8) -> float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return np.nan

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return np.nan

    if numeric > 10000:
        return numeric / scaled_divisor
    return numeric


def parse_quantity(value: object) -> float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, str):
        return float(value.strip().replace(",", "."))
    return float(value)


def parse_coordinate(value: object) -> float:
    if pd.isna(value):
        return np.nan

    try:
        integer = int(value)
    except (TypeError, ValueError):
        return np.nan

    if integer <= 0:
        return np.nan

    digits = len(str(abs(integer)))
    if digits <= 2:
        return np.nan

    return integer / (10 ** (digits - 2))


def classify_abc(cumulative_share: float) -> str:
    if cumulative_share <= 0.80:
        return "A"
    if cumulative_share <= 0.95:
        return "B"
    return "C"


def load_jazdy_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)

    df = pd.read_excel(path)
    df["trip_date_dt"] = df["DATUM"].apply(
        lambda value: parse_mixed_date(
            value,
            [
                "%d. %m. %Y",
                "%d.%m.%Y",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ],
        )
    )

    invalid_dates = int(df["trip_date_dt"].isna().sum())
    if invalid_dates:
        raise ValueError(f"Invalid trip dates found: {invalid_dates}")

    start_seconds = df["CAS_OD"].apply(parse_time_to_seconds)
    end_seconds = df["CAS_DO"].apply(parse_time_to_seconds)
    duration_minutes = (end_seconds - start_seconds) / 60
    duration_minutes = duration_minutes.where(duration_minutes >= 0, duration_minutes + 1440)

    start_lat = df["EW_START"].apply(parse_coordinate)
    start_lon = df["EL_START"].apply(parse_coordinate)
    end_lat = df["EW_END"].apply(parse_coordinate)
    end_lon = df["EL_END"].apply(parse_coordinate)

    coord_valid = (
        start_lat.between(47, 50.5)
        & start_lon.between(16, 23)
        & end_lat.between(47, 50.5)
        & end_lon.between(16, 23)
    )

    cleaned = pd.DataFrame(
        {
            "trip_date": df["trip_date_dt"].dt.strftime("%Y-%m-%d"),
            "year": df["trip_date_dt"].dt.year.astype(int),
            "month": df["trip_date_dt"].dt.month.astype(int),
            "year_month": df["trip_date_dt"].dt.to_period("M").astype(str),
            "month_name_sk": df["trip_date_dt"].dt.month.map(MONTH_NAMES_SK),
            "weekday_num": df["trip_date_dt"].dt.dayofweek.astype(int),
            "weekday_sk": df["trip_date_dt"].dt.dayofweek.map(WEEKDAY_NAMES_SK),
            "vehicle_id": df["SPZ"].astype(str),
            "time_start": df["CAS_OD"].apply(format_time),
            "time_end": df["CAS_DO"].apply(format_time),
            "trip_duration_min": duration_minutes,
            "stoppage_min": df["DOBA_STATIA_MIN"].apply(parse_decimal_or_scaled),
            "distance_m": pd.to_numeric(df["DIST_START_END_M"], errors="coerce") / 1e9,
            "distance_km": pd.to_numeric(df["DIST_START_END_M"], errors="coerce") / 1e12,
            "start_lat": start_lat,
            "start_lon": start_lon,
            "end_lat": end_lat,
            "end_lon": end_lon,
            "coord_valid": coord_valid,
        }
    )

    cleaned.loc[~cleaned["coord_valid"], ["start_lat", "start_lon", "end_lat", "end_lon"]] = np.nan
    cleaned["near_zero_trip"] = cleaned["distance_m"] < 50
    cleaned["short_trip"] = (~cleaned["near_zero_trip"]) & (cleaned["distance_km"] < 5)
    cleaned["potentially_inefficient_trip"] = (
        (~cleaned["near_zero_trip"])
        & (cleaned["distance_m"] < 500)
        & (cleaned["trip_duration_min"] >= 30)
    )
    cleaned["weekend"] = cleaned["weekday_num"] >= 5
    return cleaned


def load_material_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)

    df = pd.read_excel(path)
    df["movement_dt"] = df["DATUM"].apply(
        lambda value: parse_mixed_date(
            value,
            [
                "%d. %m. %Y %H:%M:%S",
                "%d.%m.%Y %H:%M:%S",
                "%d. %m. %Y %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ],
        )
    )

    invalid_dates = int(df["movement_dt"].isna().sum())
    if invalid_dates:
        raise ValueError(f"Invalid material dates found: {invalid_dates}")

    cleaned = pd.DataFrame(
        {
            "movement_datetime": df["movement_dt"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            "movement_date": df["movement_dt"].dt.strftime("%Y-%m-%d"),
            "year": df["movement_dt"].dt.year.astype(int),
            "month": df["movement_dt"].dt.month.astype(int),
            "year_month": df["movement_dt"].dt.to_period("M").astype(str),
            "material_number": df["MAT_NR"].astype(str),
            "material_prefix": df["MAT_NR"].astype(str).str[:8],
            "quantity_clean": df["MNOZSTVO"].apply(parse_quantity),
        }
    )

    cleaned["zero_quantity_record"] = cleaned["quantity_clean"] == 0

    material_totals = (
        cleaned.groupby("material_number", as_index=False)
        .agg(total_quantity=("quantity_clean", "sum"))
        .sort_values("total_quantity", ascending=False)
    )
    material_totals["cumulative_share"] = (
        material_totals["total_quantity"].cumsum() / material_totals["total_quantity"].sum()
    )
    material_totals["abc_segment"] = material_totals["cumulative_share"].apply(classify_abc)

    cleaned = cleaned.merge(
        material_totals[["material_number", "abc_segment"]],
        on="material_number",
        how="left",
    )
    return cleaned


def fmt_int(value: float | int) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def fmt_decimal(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def fmt_pct(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",") + " %"


def fmt_compact(value: float, digits: int = 1) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return fmt_decimal(value / 1_000_000_000, digits) + "B"
    if abs_value >= 1_000_000:
        return fmt_decimal(value / 1_000_000, digits) + "M"
    if abs_value >= 1_000:
        return fmt_decimal(value / 1_000, digits) + "K"
    if isinstance(value, float) and not value.is_integer():
        return fmt_decimal(value, digits)
    return fmt_int(value)


def month_label(value: str) -> str:
    year, month = value.split("-")
    return f"{month}/{year}"


def classify_prefix(row: pd.Series) -> str:
    if float(row["quantity_share_pct"]) >= 10:
        return "objemovo dominantny"
    if float(row["movement_share_pct"]) >= 5:
        return "frekventovany"
    if int(row["unique_material_count"]) >= 20:
        return "sirsie portfolio"
    return "stabilny"


def build_dashboard_data(jazdy: pd.DataFrame, material: pd.DataFrame) -> dict:
    jazdy["trip_date"] = pd.to_datetime(jazdy["trip_date"])
    material["movement_date"] = pd.to_datetime(material["movement_date"])

    valid_jazdy = jazdy.loc[~jazdy["near_zero_trip"]].copy()

    trips_per_vehicle = (
        jazdy.groupby("vehicle_id", as_index=False)
        .agg(
            trip_count=("vehicle_id", "size"),
            valid_trip_count=("near_zero_trip", lambda series: int((~series).sum())),
            near_zero_count=("near_zero_trip", "sum"),
            inefficient_trip_count=("potentially_inefficient_trip", "sum"),
            weekend_trip_count=("weekend", "sum"),
            total_distance_km=("distance_km", "sum"),
        )
        .sort_values(["trip_count", "vehicle_id"], ascending=[False, True])
    )

    valid_trip_distance = (
        valid_jazdy.groupby("vehicle_id", as_index=False)
        .agg(
            valid_distance_km=("distance_km", "sum"),
            avg_valid_distance_km=("distance_km", "mean"),
        )
    )

    trips_per_vehicle = trips_per_vehicle.merge(valid_trip_distance, on="vehicle_id", how="left")
    trips_per_vehicle[["valid_distance_km", "avg_valid_distance_km"]] = trips_per_vehicle[
        ["valid_distance_km", "avg_valid_distance_km"]
    ].fillna(0.0)
    trips_per_vehicle["valid_share_pct"] = (
        trips_per_vehicle["valid_trip_count"] / trips_per_vehicle["trip_count"] * 100
    ).round(1)
    trips_per_vehicle["near_zero_share_pct"] = (
        trips_per_vehicle["near_zero_count"] / trips_per_vehicle["trip_count"] * 100
    ).round(1)
    trips_per_vehicle["inefficient_share_pct"] = (
        trips_per_vehicle["inefficient_trip_count"] / trips_per_vehicle["trip_count"] * 100
    ).round(1)

    rides_monthly = (
        jazdy.groupby("year_month", as_index=False)
        .agg(trip_count=("vehicle_id", "size"))
        .sort_values("year_month")
    )
    rides_weekday = (
        jazdy.groupby(["weekday_num", "weekday_sk"], as_index=False)
        .agg(trip_count=("vehicle_id", "size"))
        .sort_values("weekday_num")
    )

    distance_band = pd.cut(
        jazdy["distance_km"],
        bins=[-0.001, 0.05, 0.5, 5, 20, 999999],
        labels=["< 0,05 km", "0,05 - 0,5 km", "0,5 - 5 km", "5 - 20 km", "20+ km"],
    )
    rides_distance = (
        distance_band.value_counts(sort=False)
        .rename_axis("distance_band")
        .reset_index(name="trip_count")
    )

    material_monthly = (
        material.groupby("year_month", as_index=False)
        .agg(
            movement_count=("material_number", "size"),
            total_quantity=("quantity_clean", "sum"),
        )
        .sort_values("year_month")
    )
    prefix_summary = (
        material.groupby("material_prefix", as_index=False)
        .agg(
            movement_count=("material_number", "size"),
            total_quantity=("quantity_clean", "sum"),
            unique_material_count=("material_number", "nunique"),
        )
        .sort_values(["movement_count", "material_prefix"], ascending=[False, True])
    )
    abc_summary = (
        material.groupby("abc_segment", as_index=False)
        .agg(
            unique_material_count=("material_number", "nunique"),
            movement_count=("material_number", "size"),
            total_quantity=("quantity_clean", "sum"),
        )
        .sort_values("abc_segment")
    )

    total_material_quantity = float(material["quantity_clean"].sum())
    prefix_summary["movement_share_pct"] = (
        prefix_summary["movement_count"] / len(material) * 100
    ).round(1)
    prefix_summary["quantity_share_pct"] = (
        prefix_summary["total_quantity"] / total_material_quantity * 100
    ).round(1)
    prefix_summary["profile"] = prefix_summary.apply(classify_prefix, axis=1)

    abc_summary["movement_share_pct"] = (abc_summary["movement_count"] / len(material) * 100).round(1)
    abc_summary["quantity_share_pct"] = (
        abc_summary["total_quantity"] / total_material_quantity * 100
    ).round(1)

    most_used_vehicle = trips_per_vehicle.iloc[0]
    least_used_vehicle = trips_per_vehicle.iloc[-1]
    most_active_weekday = rides_weekday.sort_values("trip_count", ascending=False).iloc[0]
    highest_valid_share_vehicle = trips_per_vehicle.sort_values(
        ["valid_share_pct", "trip_count", "vehicle_id"],
        ascending=[False, False, True],
    ).iloc[0]
    highest_inefficient_vehicle = trips_per_vehicle.sort_values(
        ["inefficient_share_pct", "trip_count", "vehicle_id"],
        ascending=[False, False, True],
    ).iloc[0]
    top_prefix_by_movements = prefix_summary.iloc[0]
    top_prefix_by_quantity = prefix_summary.sort_values(
        ["total_quantity", "material_prefix"],
        ascending=[False, True],
    ).iloc[0]
    top_quantity_month = material_monthly.sort_values(
        ["total_quantity", "year_month"],
        ascending=[False, True],
    ).iloc[0]

    dashboard = {
        "meta": {
            "total_records": int(len(jazdy) + len(material)),
            "dataset_cards": [
                {
                    "label": "Dataset 1",
                    "value": int(len(jazdy)),
                    "note": "Jazdy vozidiel za sledovane obdobie",
                },
                {
                    "label": "Dataset 2",
                    "value": int(len(material)),
                    "note": "Pohyby materialu za sledovane obdobie",
                },
            ],
        },
        "pochopenie_dat": {
            "jazdy": {
                "record_count": int(len(jazdy)),
                "field_count": 14,
                "date_range": [
                    jazdy["trip_date"].min().strftime("%Y-%m-%d"),
                    jazdy["trip_date"].max().strftime("%Y-%m-%d"),
                ],
                "limitations": [
                    "DIST_START_END_M vyjadruje len priamu vzdialenost medzi startom a koncom, nie realnu trasu po cestach.",
                    "V datasete nie su adresy, dovod jazdy, naklady ani prepravovany material.",
                    "Surove suradnice mali zmiesany pocet cislic a museli sa standardizovat; 2 zaznamy ostali bez validnej startovacej polohy.",
                    "Cast zaznamov ma velmi maly posun, preto sa pri interpretacii oddeluju near-zero zaznamy od beznych jazd.",
                ],
                "answerable": [
                    "vytazenost vozidiel a rozlozenie jazd v case",
                    "porovnanie mesiacov, dni v tyzdni a vzdialenostnych pasiem",
                    "odhalenie near-zero a potencialne neefektivnych zaznamov",
                ],
                "not_answerable": [
                    "realne trasy po cestach a presne naklady",
                    "dovod jazdy, vodic a prepravovany material",
                ],
            },
            "material": {
                "record_count": int(len(material)),
                "field_count": 4,
                "date_range": [
                    material["movement_date"].min().strftime("%Y-%m-%d"),
                    material["movement_date"].max().strftime("%Y-%m-%d"),
                ],
                "limitations": [
                    "Dataset obsahuje pohyby materialu, nie presny stav skladu v case.",
                    "Nie je uvedeny smer pohybu, jednotka mnozstva ani cena materialu.",
                    "Materialovy prefix je odvodeny z prvych 8 znakov kodu materialu a sluzi len ako jednoducha skupina.",
                ],
                "answerable": [
                    "top prefixy, sezonnost pohybov a objemov",
                    "ABC segmentaciu a frekvenciu pohybov materialov",
                    "identifikaciu nulovych mnozstiev a dominantnych skupin",
                ],
                "not_answerable": [
                    "presny stav skladu v case",
                    "prijem vs. vydaj, cena a skladova lokacia",
                ],
            },
        },
        "jazdy": {
            "kpi": {
                "Celkovy pocet zaznamov": int(len(jazdy)),
                "Pocet vozidiel": int(jazdy["vehicle_id"].nunique()),
                "Platne jazdy (> 50 m)": int(len(valid_jazdy)),
                "Near-zero zaznamy": int(jazdy["near_zero_trip"].sum()),
                "Priemer km na platnu jazdu": round(valid_jazdy["distance_km"].mean(), 2),
                "Median km na platnu jazdu": round(valid_jazdy["distance_km"].median(), 2),
            },
            "totals": {
                "valid_distance_km": round(float(valid_jazdy["distance_km"].sum()), 2),
                "avg_trips_per_vehicle": round(float(len(jazdy) / jazdy["vehicle_id"].nunique()), 1),
                "near_zero_share_pct": round(float(jazdy["near_zero_trip"].mean() * 100), 1),
                "short_trip_count": int(jazdy["short_trip"].sum()),
                "weekend_trip_count": int(jazdy["weekend"].sum()),
            },
            "charts": {
                "jazdy_podla_mesiaca": [
                    {"label": month_label(row.year_month), "value": int(row.trip_count)}
                    for row in rides_monthly.itertuples(index=False)
                ],
                "jazdy_podla_dna": [
                    {"label": row.weekday_sk, "value": int(row.trip_count)}
                    for row in rides_weekday.itertuples(index=False)
                ],
                "top_vozidla_podla_poctu_jazd": [
                    {"label": row.vehicle_id, "value": int(row.trip_count)}
                    for row in trips_per_vehicle.head(8).itertuples(index=False)
                ],
                "rozdelenie_podla_vzdialenosti": [
                    {"label": row.distance_band, "value": int(row.trip_count)}
                    for row in rides_distance.itertuples(index=False)
                ],
            },
            "vehicle_table": [
                {
                    "vehicle_id": row.vehicle_id,
                    "trip_count": int(row.trip_count),
                    "valid_trip_count": int(row.valid_trip_count),
                    "valid_share_pct": float(row.valid_share_pct),
                    "near_zero_share_pct": float(row.near_zero_share_pct),
                    "inefficient_share_pct": float(row.inefficient_share_pct),
                    "valid_distance_km": round(float(row.valid_distance_km), 1),
                    "avg_valid_distance_km": round(float(row.avg_valid_distance_km), 2),
                }
                for row in trips_per_vehicle.itertuples(index=False)
            ],
            "comment": (
                f"Najviac jazd malo vozidlo {most_used_vehicle.vehicle_id} ({int(most_used_vehicle.trip_count)}), "
                f"najmenej {least_used_vehicle.vehicle_id} ({int(least_used_vehicle.trip_count)}). "
                f"Najsilnejsi den je {most_active_weekday.weekday_sk}. "
                f"Najvyssi podiel platnych jazd ma {highest_valid_share_vehicle.vehicle_id} "
                f"({highest_valid_share_vehicle.valid_share_pct:.1f} %). "
                f"Near-zero zaznamy tvoria {jazdy['near_zero_trip'].mean() * 100:.1f} % vsetkych zaznamov."
            ),
        },
        "material": {
            "kpi": {
                "Celkovy pocet pohybov": int(len(material)),
                "Pocet materialov": int(material["material_number"].nunique()),
                "Pocet prefixov": int(material["material_prefix"].nunique()),
                "Celkove mnozstvo": round(total_material_quantity, 0),
                "Priemerne mnozstvo": round(float(material["quantity_clean"].mean()), 1),
                "Median mnozstva": round(float(material["quantity_clean"].median()), 1),
            },
            "totals": {
                "zero_quantity_record_count": int(material["zero_quantity_record"].sum()),
                "top_quantity_month": month_label(top_quantity_month.year_month),
                "top_quantity_month_value": round(float(top_quantity_month.total_quantity), 1),
            },
            "charts": {
                "pohyby_podla_mesiaca": [
                    {"label": month_label(row.year_month), "value": int(row.movement_count)}
                    for row in material_monthly.itertuples(index=False)
                ],
                "mnozstvo_podla_mesiaca": [
                    {"label": month_label(row.year_month), "value": round(float(row.total_quantity), 1)}
                    for row in material_monthly.itertuples(index=False)
                ],
                "top_prefixy_podla_pohybov": [
                    {"label": row.material_prefix, "value": int(row.movement_count)}
                    for row in prefix_summary.head(8).itertuples(index=False)
                ],
                "abc_segmenty": [
                    {"label": row.abc_segment, "value": int(row.unique_material_count)}
                    for row in abc_summary.itertuples(index=False)
                ],
            },
            "prefix_table": [
                {
                    "material_prefix": row.material_prefix,
                    "movement_count": int(row.movement_count),
                    "movement_share_pct": float(row.movement_share_pct),
                    "total_quantity": round(float(row.total_quantity), 1),
                    "quantity_share_pct": float(row.quantity_share_pct),
                    "unique_material_count": int(row.unique_material_count),
                    "profile": row.profile,
                }
                for row in prefix_summary.head(10).itertuples(index=False)
            ],
            "comment": (
                f"Najaktivnejsi prefix podla poctu pohybov je {top_prefix_by_movements.material_prefix} "
                f"({int(top_prefix_by_movements.movement_count)} pohybov). "
                f"Podla celkoveho mnozstva jednoznacne dominuje {top_prefix_by_quantity.material_prefix} "
                f"({top_prefix_by_quantity.total_quantity:,.1f}). "
                f"Najsilnejsi mesiac podla objemu je {month_label(top_quantity_month.year_month)}."
            ),
        },
        "pokrocilejsia_analytika": {
            "jazdy": {
                "potentially_inefficient_trip_count": int(jazdy["potentially_inefficient_trip"].sum()),
                "short_trip_count": int(jazdy["short_trip"].sum()),
                "near_zero_trip_count": int(jazdy["near_zero_trip"].sum()),
                "weekend_trip_count": int(jazdy["weekend"].sum()),
                "description": (
                    "Heuristika oznacuje zaznamy s trvanim aspon 30 minut a so zmenou polohy pod 0,5 km. "
                    "Ide len o signal na kontrolu, nie o dokazanu neefektivitu."
                ),
                "top_vehicle_shares": [
                    {
                        "vehicle_id": row.vehicle_id,
                        "trip_count": int(row.trip_count),
                        "inefficient_trip_count": int(row.inefficient_trip_count),
                        "inefficient_share_pct": float(row.inefficient_share_pct),
                    }
                    for row in trips_per_vehicle.sort_values(
                        ["inefficient_share_pct", "trip_count", "vehicle_id"],
                        ascending=[False, False, True],
                    ).head(5).itertuples(index=False)
                ],
                "watch_vehicle": {
                    "vehicle_id": highest_inefficient_vehicle.vehicle_id,
                    "share_pct": float(highest_inefficient_vehicle.inefficient_share_pct),
                },
            },
            "material": {
                "abc_summary": [
                    {
                        "abc_segment": row.abc_segment,
                        "unique_material_count": int(row.unique_material_count),
                        "movement_count": int(row.movement_count),
                        "movement_share_pct": float(row.movement_share_pct),
                        "total_quantity": round(float(row.total_quantity), 1),
                        "quantity_share_pct": float(row.quantity_share_pct),
                    }
                    for row in abc_summary.itertuples(index=False)
                ],
                "zero_quantity_record_count": int(material["zero_quantity_record"].sum()),
                "description": (
                    "Pouzita je jednoducha ABC segmentacia podla kumulativneho podielu na celkovom mnozstve. "
                    "Je interpretovatelnejsia ako clustering a lahsie sa obhajuje v studentskom projekte."
                ),
            },
        },
        "porovnanie_html_vs_tableau": {
            "message": (
                "HTML je doplnkovy artefakt postaveny na tych istych datasetoch. Ak sa cisla v HTML a Tableau lisia, "
                "najprv treba skontrolovat filtre, typy datumov a rozdiel medzi COUNT a COUNTD. "
                "Pri finalnej obhajobe ma prednost validacia v Tableau."
            )
        },
    }

    return dashboard


def render_field_rows(fields: list[dict]) -> str:
    rows = [
        """
        <div class="field-row field-head">
          <div>Pole</div>
          <div>Popis</div>
          <div>Typ</div>
        </div>
        """
    ]
    for field in fields:
        rows.append(
            f"""
            <div class="field-row">
              <div class="field-name">{escape(field["name"])}</div>
              <div class="field-meaning">{escape(field["description"])}</div>
              <div class="field-type">{escape(field["type"])}</div>
            </div>
            """
        )
    return "".join(rows)


def render_dataset_profile(
    title: str,
    intro: str,
    fields: list[dict],
    limitations: list[str],
) -> str:
    limitations_html = "".join(f"<li>{escape(item)}</li>" for item in limitations)
    return f"""
    <div class="field-card">
      <div class="card-title">{escape(title)}</div>
      <p class="card-intro">{escape(intro)}</p>
      <div class="field-grid">
        {render_field_rows(fields)}
      </div>
      <div class="limit-box">
        <div class="limit-title">Limity interpretacie</div>
        <ul>{limitations_html}</ul>
      </div>
    </div>
    """


def render_kpi_cards(cards: list[dict]) -> str:
    items = []
    for card in cards:
        items.append(
            f"""
            <div class="kpi-card" style="--accent:{card["color"]}">
              <div class="kpi-label">{escape(card["label"])}</div>
              <div class="kpi-value">{escape(card["value"])}</div>
              <div class="kpi-sub">{escape(card["sub"])}</div>
            </div>
            """
        )
    return "".join(items)


def render_header_cards(cards: list[dict]) -> str:
    items = []
    for card in cards:
        items.append(
            f"""
            <div class="meta-card">
              <div class="meta-label">{escape(card["label"])}</div>
              <div class="meta-value">{fmt_int(card["value"])}</div>
              <div class="meta-note">{escape(card["note"])}</div>
            </div>
            """
        )
    return "".join(items)


def render_table(title: str, headers: list[str], rows: list[list[str]], intro: str | None = None) -> str:
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    row_html = []
    for row in rows:
        cells = "".join(f"<td>{escape(str(cell))}</td>" for cell in row)
        row_html.append(f"<tr>{cells}</tr>")

    intro_html = f'<p class="table-intro">{escape(intro)}</p>' if intro else ""
    return f"""
    <div class="card table-card">
      <div class="card-title">{escape(title)}</div>
      {intro_html}
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>{header_html}</tr></thead>
          <tbody>{''.join(row_html)}</tbody>
        </table>
      </div>
    </div>
    """


def render_signal_tiles(signal_tiles: list[dict]) -> str:
    tiles = []
    for tile in signal_tiles:
        tiles.append(
            f"""
            <div class="signal-tile">
              <div class="signal-label">{escape(tile["label"])}</div>
              <div class="signal-value">{escape(tile["value"])}</div>
              <div class="signal-sub">{escape(tile["sub"])}</div>
            </div>
            """
        )
    return "".join(tiles)


def render_recommendation_list(items: list[str]) -> str:
    return "<ul class=\"recom-list\">" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def build_html(dashboard: dict) -> str:
    understanding = dashboard["pochopenie_dat"]
    jazdy = dashboard["jazdy"]
    material = dashboard["material"]
    advanced = dashboard["pokrocilejsia_analytika"]
    meta = dashboard["meta"]

    header_total = fmt_int(meta["total_records"])
    header_cards = render_header_cards(meta["dataset_cards"])
    header_sub = (
        f"Jazdy {understanding['jazdy']['date_range'][0]} - {understanding['jazdy']['date_range'][1]} "
        f"| Material {understanding['material']['date_range'][0]} - {understanding['material']['date_range'][1]} "
        f"| {header_total} zaznamov"
    )

    understanding_section = f"""
    <section id="tab-pochopenie" class="section active">
      <div class="section-title">Pochopenie dat</div>
      <p class="section-copy">
        Najprv treba povedat, co datasety naozaj obsahuju, na co sa hodia a kde sa interpretacia musi zastavit.
      </p>

      <div class="grid-2">
        {render_dataset_profile(
            "Dataset 1 - Jazdy vozidiel",
            f"Excel obsahuje {fmt_int(understanding['jazdy']['record_count'])} riadkov a {fmt_int(understanding['jazdy']['field_count'])} povodnych poli. Obdobie: {understanding['jazdy']['date_range'][0]} az {understanding['jazdy']['date_range'][1]}.",
            JAZDY_FIELDS,
            understanding["jazdy"]["limitations"],
        )}
        {render_dataset_profile(
            "Dataset 2 - Pohyby materialu",
            f"Excel obsahuje {fmt_int(understanding['material']['record_count'])} riadkov a {fmt_int(understanding['material']['field_count'])} povodne polia. Obdobie: {understanding['material']['date_range'][0]} az {understanding['material']['date_range'][1]}.",
            MATERIAL_FIELDS,
            understanding["material"]["limitations"],
        )}
      </div>

      <div class="insight-grid">
        <div class="insight-item info">
          <strong>Co vieme zodpovedat z jazd</strong>
          {escape("; ".join(understanding["jazdy"]["answerable"]))}.
        </div>
        <div class="insight-item info">
          <strong>Co vieme zodpovedat z materialu</strong>
          {escape("; ".join(understanding["material"]["answerable"]))}.
        </div>
        <div class="insight-item warn">
          <strong>Co z jazd nevieme dokazat</strong>
          {escape("; ".join(understanding["jazdy"]["not_answerable"]))}.
        </div>
        <div class="insight-item warn">
          <strong>Co z materialu nevieme zistit</strong>
          {escape("; ".join(understanding["material"]["not_answerable"]))}.
        </div>
      </div>
    </section>
    """

    jazdy_kpis = render_kpi_cards(
        [
            {
                "label": "Zaznamy jazd",
                "value": fmt_int(jazdy["kpi"]["Celkovy pocet zaznamov"]),
                "sub": "kompletne obdobie 2024",
                "color": "var(--accent1)",
            },
            {
                "label": "Vozidla",
                "value": fmt_int(jazdy["kpi"]["Pocet vozidiel"]),
                "sub": "unikatne SPZ v datasete",
                "color": "var(--accent2)",
            },
            {
                "label": "Platne jazdy",
                "value": fmt_int(jazdy["kpi"]["Platne jazdy (> 50 m)"]),
                "sub": fmt_pct(
                    jazdy["kpi"]["Platne jazdy (> 50 m)"] / jazdy["kpi"]["Celkovy pocet zaznamov"] * 100
                ),
                "color": "var(--accent3)",
            },
            {
                "label": "Near-zero podiel",
                "value": fmt_pct(jazdy["totals"]["near_zero_share_pct"]),
                "sub": fmt_int(jazdy["kpi"]["Near-zero zaznamy"]) + " zaznamov",
                "color": "var(--accent4)",
            },
            {
                "label": "Priemer km / platna jazda",
                "value": fmt_decimal(jazdy["kpi"]["Priemer km na platnu jazdu"], 2),
                "sub": "median " + fmt_decimal(jazdy["kpi"]["Median km na platnu jazdu"], 2),
                "color": "var(--accent1)",
            },
            {
                "label": "Celkova vzdialenost",
                "value": fmt_compact(jazdy["totals"]["valid_distance_km"], 1) + " km",
                "sub": "sucet len pre platne jazdy",
                "color": "var(--accent2)",
            },
        ]
    )

    vehicle_rows = [
        [
            item["vehicle_id"],
            fmt_int(item["trip_count"]),
            fmt_pct(item["valid_share_pct"]),
            fmt_pct(item["near_zero_share_pct"]),
            fmt_decimal(item["valid_distance_km"], 1) + " km",
            fmt_decimal(item["avg_valid_distance_km"], 2) + " km",
            fmt_pct(item["inefficient_share_pct"]),
        ]
        for item in jazdy["vehicle_table"][:10]
    ]

    jazdy_section = f"""
    <section id="tab-jazdy" class="section">
      <div class="section-title">Jazdy vozidiel</div>
      <p class="section-copy">{escape(jazdy["comment"])}</p>

      <div class="kpi-row">{jazdy_kpis}</div>

      <div class="grid-2">
        <div class="card canvas-card">
          <div class="card-title">Pocet zaznamov podla mesiaca</div>
          <canvas id="chartMonthlyTrips" height="220"></canvas>
        </div>
        <div class="card canvas-card">
          <div class="card-title">Pocet zaznamov podla dna v tyzdni</div>
          <canvas id="chartWeekdayTrips" height="220"></canvas>
        </div>
      </div>

      <div class="grid-13">
        <div class="card canvas-card">
          <div class="card-title">Rozdelenie podla priamej vzdialenosti</div>
          <canvas id="chartTripDistance" height="260"></canvas>
        </div>
        <div class="card canvas-card">
          <div class="card-title">Top vozidla podla poctu zaznamov</div>
          <canvas id="chartTopVehicles" height="260"></canvas>
        </div>
      </div>

      {render_table(
          "Detail vozidiel",
          [
              "Vozidlo",
              "Zaznamy",
              "Platne jazdy",
              "Near-zero",
              "Platna vzdialenost",
              "Priemer / platna jazda",
              "Oznacene heuristikou",
          ],
          vehicle_rows,
          intro="Tabulka kombinuje vyuzitie flotily, podiel near-zero zaznamov a heuristicke rizikove spravanie.",
      )}

      <div class="insight">
        <strong>Rychla interpretacia:</strong>
        Pri tejto teme je dolezite filtrovat near-zero zaznamy osobitne. Inak budu skreslovat priemerne vzdialenosti,
        porovnanie vozidiel aj interpretaciu vyuzitia flotily.
      </div>
    </section>
    """

    material_kpis = render_kpi_cards(
        [
            {
                "label": "Pohyby materialu",
                "value": fmt_int(material["kpi"]["Celkovy pocet pohybov"]),
                "sub": "roky 2023 az 2025",
                "color": "var(--accent3)",
            },
            {
                "label": "Unikatne materialy",
                "value": fmt_int(material["kpi"]["Pocet materialov"]),
                "sub": fmt_int(material["kpi"]["Pocet prefixov"]) + " prefixov",
                "color": "var(--accent1)",
            },
            {
                "label": "Celkove mnozstvo",
                "value": fmt_compact(material["kpi"]["Celkove mnozstvo"], 1),
                "sub": "sumar cez vsetky pohyby",
                "color": "var(--accent2)",
            },
            {
                "label": "Priemerne mnozstvo",
                "value": fmt_decimal(material["kpi"]["Priemerne mnozstvo"], 1),
                "sub": "median " + fmt_decimal(material["kpi"]["Median mnozstva"], 1),
                "color": "var(--accent4)",
            },
            {
                "label": "Nulove mnozstvo",
                "value": fmt_int(material["totals"]["zero_quantity_record_count"]),
                "sub": "zaznamov na kontrolu",
                "color": "var(--accent1)",
            },
            {
                "label": "Najsilnejsi objemovy mesiac",
                "value": material["totals"]["top_quantity_month"],
                "sub": fmt_compact(material["totals"]["top_quantity_month_value"], 1),
                "color": "var(--accent2)",
            },
        ]
    )

    prefix_rows = [
        [
            item["material_prefix"],
            fmt_int(item["movement_count"]),
            fmt_pct(item["movement_share_pct"]),
            fmt_compact(item["total_quantity"], 1),
            fmt_pct(item["quantity_share_pct"]),
            fmt_int(item["unique_material_count"]),
            item["profile"],
        ]
        for item in material["prefix_table"]
    ]

    material_section = f"""
    <section id="tab-material" class="section">
      <div class="section-title">Pohyby materialu</div>
      <p class="section-copy">{escape(material["comment"])}</p>

      <div class="kpi-row">{material_kpis}</div>

      <div class="grid-2">
        <div class="card canvas-card">
          <div class="card-title">Pohyby materialu podla mesiaca</div>
          <canvas id="chartMaterialMoves" height="220"></canvas>
        </div>
        <div class="card canvas-card">
          <div class="card-title">Celkove mnozstvo podla mesiaca</div>
          <canvas id="chartMaterialQty" height="220"></canvas>
        </div>
      </div>

      <div class="grid-13">
        <div class="card canvas-card">
          <div class="card-title">ABC segmenty podla poctu materialov</div>
          <canvas id="chartAbcSegments" height="260"></canvas>
        </div>
        <div class="card canvas-card">
          <div class="card-title">Top prefixy podla poctu pohybov</div>
          <canvas id="chartTopPrefixes" height="260"></canvas>
        </div>
      </div>

      {render_table(
          "Detail top prefixov",
          [
              "Prefix",
              "Pohyby",
              "Podiel pohybov",
              "Celkove mnozstvo",
              "Podiel mnozstva",
              "Unikatne materialy",
              "Profil",
          ],
          prefix_rows,
          intro="Tabulka odlisuje prefixy, ktore su frekvencne dominantne, od prefixov, ktore nesu vacsinu objemu.",
      )}

      <div class="insight">
        <strong>Rychla interpretacia:</strong>
        Pocet pohybov a celkove mnozstvo treba citat oddelene. Prefix, ktory vedie v pocte pohybov, nemusi byt
        objemovo najdolezitejsi a naopak.
      </div>
    </section>
    """

    trip_signal_tiles = render_signal_tiles(
        [
            {
                "label": "Near-zero zaznamy",
                "value": fmt_int(advanced["jazdy"]["near_zero_trip_count"]),
                "sub": "samostatny filter pre interpretaciu",
            },
            {
                "label": "Kratke jazdy < 5 km",
                "value": fmt_int(advanced["jazdy"]["short_trip_count"]),
                "sub": "bez near-zero zaznamov",
            },
            {
                "label": "Oznacene heuristikou",
                "value": fmt_int(advanced["jazdy"]["potentially_inefficient_trip_count"]),
                "sub": "signal na manualnu kontrolu",
            },
            {
                "label": "Vikendove zaznamy",
                "value": fmt_int(advanced["jazdy"]["weekend_trip_count"]),
                "sub": "So + Ne spolu",
            },
        ]
    )

    vehicle_watch_rows = [
        [
            item["vehicle_id"],
            fmt_int(item["trip_count"]),
            fmt_int(item["inefficient_trip_count"]),
            fmt_pct(item["inefficient_share_pct"]),
        ]
        for item in advanced["jazdy"]["top_vehicle_shares"]
    ]

    abc_rows = [
        [
            item["abc_segment"],
            fmt_int(item["unique_material_count"]),
            fmt_int(item["movement_count"]),
            fmt_pct(item["movement_share_pct"]),
            fmt_compact(item["total_quantity"], 1),
            fmt_pct(item["quantity_share_pct"]),
        ]
        for item in advanced["material"]["abc_summary"]
    ]

    advanced_section = f"""
    <section id="tab-pokrocila" class="section">
      <div class="section-title">Pokrocila analytika</div>
      <p class="section-copy">
        Tato cast nepretlaca zbytocne scenare. Zvyraznuje iba tie signaly, ktore sa daju obhajit na zaklade aktualnych datasetov.
      </p>

      <div class="grid-2">
        <div class="adv-box">
          <div class="card-title">Rizikove signaly v jazdach</div>
          <p class="adv-copy">{escape(advanced["jazdy"]["description"])}</p>
          <div class="signal-grid">{trip_signal_tiles}</div>
          {render_table(
              "Vozidla s najvyssim podielom oznacenych zaznamov",
              ["Vozidlo", "Vsetky zaznamy", "Oznacene", "Podiel"],
              vehicle_watch_rows,
              intro=(
                  f"Na manualnu kontrolu je vhodne zacat pri vozidle "
                  f"{advanced['jazdy']['watch_vehicle']['vehicle_id']} "
                  f"({fmt_pct(advanced['jazdy']['watch_vehicle']['share_pct'])})."
              ),
          )}
        </div>

        <div class="adv-box">
          <div class="card-title">ABC segmentacia materialu</div>
          <p class="adv-copy">{escape(advanced["material"]["description"])}</p>
          {render_table(
              "Segmenty A / B / C",
              [
                  "Segment",
                  "Materialy",
                  "Pohyby",
                  "Podiel pohybov",
                  "Celkove mnozstvo",
                  "Podiel mnozstva",
              ],
              abc_rows,
              intro=(
                  f"Nulove mnozstvo sa v cistenych datach objavilo v "
                  f"{fmt_int(advanced['material']['zero_quantity_record_count'])} zaznamoch."
              ),
          )}
        </div>
      </div>

      <div class="grid-2">
        <div class="card canvas-card">
          <div class="card-title">Podiel oznacenych zaznamov podla vozidla</div>
          <canvas id="chartInefficientVehicles" height="220"></canvas>
        </div>
        <div class="card canvas-card">
          <div class="card-title">Podiel mnozstva podla ABC segmentu</div>
          <canvas id="chartAbcQtyShare" height="220"></canvas>
        </div>
      </div>

      <div class="adv-box">
        <div class="card-title">Odporucania pre finalny dashboard</div>
        {render_recommendation_list(
            [
                "Drzat near-zero jazdy ako samostatny filter, nie miesat ich do hlavnych vzdialenostnych KPI.",
                "V Tableau ukazat vedla seba pocet pohybov aj celkove mnozstvo, lebo kazdy pohlad hovori iny pribeh.",
                "Na detailnej kontrole zacat pri vozidlach s najvyssim podielom heuristicky oznacenych zaznamov.",
                "Pri materiale odlisit frekvencne dominantne prefixy od prefixov, ktore nesu vacsinu objemu.",
            ]
        )}
      </div>

      <div class="card validation-card">
        <div class="card-title">HTML vs Tableau validation</div>
        <p class="section-copy">{escape(dashboard["porovnanie_html_vs_tableau"]["message"])}</p>
        <ul class="validation-list">
          <li>HTML je doplnok postaveny na tych istych datasetoch ako Tableau analyza.</li>
          <li>Pri rozdiele treba porovnat filtre, datumove typy a rozdiel medzi COUNT a COUNTD.</li>
          <li>Do finalnej obhajoby ma prednost validacia v Tableau.</li>
        </ul>
      </div>
    </section>
    """

    json_blob = json.dumps(dashboard, ensure_ascii=False)

    template = """<!DOCTYPE html>
<html lang="sk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Analyza datasetov - HTML prehlad</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@500;700;800&family=DM+Sans:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #08111f;
      --bg2: #0d182b;
      --surface: rgba(15, 25, 43, 0.88);
      --surface-strong: rgba(18, 30, 51, 0.98);
      --surface-soft: rgba(21, 34, 58, 0.78);
      --border: rgba(88, 118, 165, 0.24);
      --text: #ebf1fb;
      --text-soft: #9db1ca;
      --text-dim: #6f87a6;
      --accent1: #00d4ff;
      --accent2: #ff7a45;
      --accent3: #71f3ab;
      --accent4: #ffd166;
      --shadow: 0 18px 60px rgba(0, 0, 0, 0.28);
      --radius-lg: 18px;
      --radius-md: 14px;
      --radius-sm: 10px;
      --font-head: "Syne", sans-serif;
      --font-body: "DM Sans", sans-serif;
      --font-mono: "DM Mono", monospace;
    }

    * {
      box-sizing: border-box;
    }

    html {
      scroll-behavior: smooth;
    }

    body {
      margin: 0;
      background:
        radial-gradient(circle at top right, rgba(0, 212, 255, 0.08), transparent 28%),
        radial-gradient(circle at left 15%, rgba(255, 122, 69, 0.07), transparent 24%),
        linear-gradient(180deg, var(--bg2) 0%, var(--bg) 45%, #060c17 100%);
      color: var(--text);
      font-family: var(--font-body);
      line-height: 1.6;
      min-height: 100vh;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(157, 177, 202, 0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(157, 177, 202, 0.03) 1px, transparent 1px);
      background-size: 32px 32px;
      mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.45), transparent 72%);
    }

    header {
      position: relative;
      overflow: hidden;
      padding: 40px 32px 28px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(135deg, rgba(10, 20, 36, 0.96), rgba(11, 25, 45, 0.88));
    }

    header::before,
    header::after {
      content: "";
      position: absolute;
      border-radius: 999px;
      filter: blur(8px);
    }

    header::before {
      width: 320px;
      height: 320px;
      right: -110px;
      top: -120px;
      background: radial-gradient(circle, rgba(0, 212, 255, 0.18), transparent 70%);
    }

    header::after {
      width: 240px;
      height: 240px;
      left: 18%;
      bottom: -150px;
      background: radial-gradient(circle, rgba(255, 122, 69, 0.12), transparent 70%);
    }

    .page-shell {
      max-width: 1380px;
      margin: 0 auto;
      position: relative;
      z-index: 1;
    }

    h1 {
      margin: 0 0 8px;
      font-family: var(--font-head);
      font-size: clamp(34px, 5vw, 54px);
      letter-spacing: -0.03em;
      line-height: 1;
    }

    h1 span {
      color: var(--accent1);
    }

    .header-sub {
      color: var(--text-soft);
      max-width: 980px;
      font-size: 14px;
      font-family: var(--font-mono);
    }

    .meta-strip {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 24px;
    }

    .meta-card {
      padding: 14px 16px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
      background: rgba(13, 24, 43, 0.72);
      box-shadow: var(--shadow);
    }

    .meta-label {
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 1.2px;
      text-transform: uppercase;
      color: var(--text-dim);
      margin-bottom: 6px;
    }

    .meta-value {
      font-family: var(--font-head);
      font-size: 20px;
      line-height: 1.1;
    }

    .meta-note {
      margin-top: 6px;
      color: var(--text-soft);
      font-size: 12px;
    }

    .tabs-wrap {
      position: sticky;
      top: 0;
      z-index: 30;
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(16px);
      background: rgba(8, 17, 31, 0.78);
    }

    .tabs {
      display: flex;
      gap: 8px;
      padding: 0 32px;
      overflow-x: auto;
      scrollbar-width: thin;
    }

    .tab {
      appearance: none;
      border: 0;
      border-bottom: 2px solid transparent;
      background: transparent;
      color: var(--text-dim);
      cursor: pointer;
      font-family: var(--font-head);
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0.02em;
      padding: 16px 18px 14px;
      transition: color 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
      white-space: nowrap;
    }

    .tab:hover {
      color: var(--text);
      transform: translateY(-1px);
    }

    .tab.active {
      color: var(--accent1);
      border-bottom-color: var(--accent1);
    }

    main {
      max-width: 1380px;
      margin: 0 auto;
      padding: 30px 32px 48px;
    }

    .section {
      display: none;
      animation: fadeIn 0.28s ease;
    }

    .section.active {
      display: block;
    }

    @keyframes fadeIn {
      from {
        opacity: 0;
        transform: translateY(6px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .section-title {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
      font-family: var(--font-head);
      font-size: 24px;
      letter-spacing: -0.02em;
    }

    .section-title::before {
      content: "";
      width: 36px;
      height: 3px;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent1), transparent);
    }

    .section-copy {
      margin: 0 0 22px;
      color: var(--text-soft);
      max-width: 980px;
      font-size: 14px;
    }

    .grid-2,
    .grid-13,
    .kpi-row,
    .insight-grid,
    .signal-grid {
      display: grid;
      gap: 18px;
    }

    .grid-2 {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-bottom: 18px;
    }

    .grid-13 {
      grid-template-columns: minmax(280px, 0.95fr) minmax(380px, 1.35fr);
      margin-bottom: 18px;
    }

    .kpi-row {
      grid-template-columns: repeat(6, minmax(0, 1fr));
      margin-bottom: 18px;
    }

    .insight-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 18px;
    }

    .signal-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin: 18px 0;
    }

    .card,
    .field-card,
    .adv-box {
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: var(--surface);
      box-shadow: var(--shadow);
    }

    .card,
    .field-card,
    .adv-box {
      padding: 22px;
    }

    .kpi-card {
      position: relative;
      overflow: hidden;
      padding: 18px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(19, 32, 54, 0.94), rgba(14, 25, 43, 0.92));
      box-shadow: var(--shadow);
    }

    .kpi-card::before {
      content: "";
      position: absolute;
      inset: 0 0 auto;
      height: 3px;
      background: var(--accent);
    }

    .kpi-label,
    .signal-label,
    .limit-title,
    .field-head,
    .data-table th {
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 1.2px;
      text-transform: uppercase;
    }

    .kpi-label {
      color: var(--text-dim);
      margin-bottom: 10px;
    }

    .kpi-value {
      font-family: var(--font-head);
      font-size: 30px;
      line-height: 1;
      letter-spacing: -0.03em;
      margin-bottom: 8px;
    }

    .kpi-sub {
      color: var(--text-soft);
      font-size: 12px;
    }

    .card-title {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 14px;
      color: var(--text-soft);
      font-family: var(--font-head);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .card-title::before {
      content: "";
      width: 3px;
      height: 14px;
      border-radius: 999px;
      background: var(--accent1);
      flex-shrink: 0;
    }

    .card-intro,
    .adv-copy,
    .table-intro {
      margin: 0 0 16px;
      color: var(--text-soft);
      font-size: 13px;
    }

    .field-grid {
      display: grid;
      gap: 0;
    }

    .field-row {
      display: grid;
      grid-template-columns: 170px 1fr 92px;
      gap: 14px;
      padding: 10px 0;
      border-bottom: 1px solid rgba(88, 118, 165, 0.16);
      align-items: start;
    }

    .field-row:last-child {
      border-bottom: 0;
    }

    .field-head {
      color: var(--text-dim);
    }

    .field-name {
      color: var(--accent1);
      font-family: var(--font-mono);
      font-size: 12px;
    }

    .field-meaning {
      color: var(--text-soft);
      font-size: 13px;
    }

    .field-type {
      display: inline-flex;
      justify-content: center;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(255, 209, 102, 0.09);
      border: 1px solid rgba(255, 209, 102, 0.18);
      color: var(--accent4);
      font-family: var(--font-mono);
      font-size: 10px;
    }

    .limit-box {
      margin-top: 18px;
      padding: 16px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(255, 122, 69, 0.2);
      background: rgba(255, 122, 69, 0.08);
    }

    .limit-title {
      color: var(--accent2);
      margin-bottom: 8px;
    }

    ul {
      margin: 0;
      padding-left: 18px;
    }

    li + li {
      margin-top: 6px;
    }

    .insight,
    .insight-item {
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
      background: var(--surface-soft);
      padding: 16px 18px;
      color: var(--text-soft);
      font-size: 13px;
    }

    .insight {
      margin-top: 18px;
      border-left: 3px solid var(--accent2);
    }

    .insight strong,
    .insight-item strong {
      display: block;
      margin-bottom: 6px;
      color: var(--text);
      font-family: var(--font-head);
      font-size: 13px;
    }

    .insight-item.info {
      border-left: 3px solid var(--accent1);
    }

    .insight-item.warn {
      border-left: 3px solid var(--accent2);
    }

    .canvas-card canvas {
      width: 100%;
      display: block;
    }

    .chart-tooltip {
      position: fixed;
      left: 0;
      top: 0;
      z-index: 90;
      min-width: 126px;
      padding: 10px 12px;
      border: 1px solid rgba(157, 177, 202, 0.18);
      border-radius: 12px;
      background: rgba(6, 12, 22, 0.96);
      box-shadow: 0 16px 34px rgba(0, 0, 0, 0.34);
      pointer-events: none;
      opacity: 0;
      transform: translate3d(0, 6px, 0);
      transition: opacity 0.12s ease, transform 0.12s ease;
    }

    .chart-tooltip.visible {
      opacity: 1;
      transform: translate3d(0, 0, 0);
    }

    .chart-tooltip-label {
      margin-bottom: 4px;
      color: var(--text-soft);
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 1.1px;
    }

    .chart-tooltip-value {
      color: var(--text);
      font-family: var(--font-head);
      font-size: 18px;
      line-height: 1.1;
    }

    .table-card {
      margin-bottom: 18px;
    }

    .table-wrap {
      overflow-x: auto;
    }

    .data-table {
      width: 100%;
      border-collapse: collapse;
      min-width: 640px;
    }

    .data-table th {
      padding: 10px 10px 12px;
      text-align: left;
      color: var(--text-dim);
      border-bottom: 1px solid rgba(88, 118, 165, 0.26);
    }

    .data-table td {
      padding: 10px;
      border-bottom: 1px solid rgba(88, 118, 165, 0.12);
      color: var(--text);
      font-size: 13px;
      white-space: nowrap;
    }

    .data-table tbody tr:hover td {
      background: rgba(0, 212, 255, 0.03);
    }

    .signal-tile {
      padding: 16px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(88, 118, 165, 0.2);
      background: linear-gradient(180deg, rgba(17, 30, 52, 0.96), rgba(13, 24, 43, 0.94));
    }

    .signal-label {
      color: var(--text-dim);
      margin-bottom: 8px;
    }

    .signal-value {
      font-family: var(--font-head);
      font-size: 26px;
      line-height: 1;
      margin-bottom: 6px;
    }

    .signal-sub {
      color: var(--text-soft);
      font-size: 12px;
    }

    .recom-list,
    .validation-list {
      margin: 0;
      padding-left: 18px;
      color: var(--text-soft);
      font-size: 13px;
    }

    .validation-card {
      margin-top: 18px;
    }

    .footer-note {
      margin-top: 24px;
      color: var(--text-dim);
      font-size: 12px;
    }

    @media (max-width: 1180px) {
      .kpi-row {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
    }

    @media (max-width: 960px) {
      header,
      main {
        padding-left: 20px;
        padding-right: 20px;
      }

      .tabs {
        padding-left: 20px;
        padding-right: 20px;
      }

      .grid-2,
      .grid-13,
      .insight-grid {
        grid-template-columns: 1fr;
      }

      .meta-strip {
        grid-template-columns: 1fr;
      }
    }

    @media (max-width: 760px) {
      .kpi-row,
      .signal-grid {
        grid-template-columns: 1fr;
      }

      .field-row {
        grid-template-columns: 1fr;
      }

      .data-table {
        min-width: 560px;
      }

      .tab {
        padding-left: 10px;
        padding-right: 10px;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="page-shell">
      <h1>Analyticky <span>Dashboard</span></h1>
      <div class="header-sub">__HEADER_SUB__</div>

      <div class="meta-strip">__HEADER_DATASET_CARDS__</div>
    </div>
  </header>

  <div class="tabs-wrap">
    <div class="page-shell">
      <div class="tabs" role="tablist" aria-label="Dashboard sections">
        <button class="tab active" data-tab="pochopenie" aria-selected="true">Pochopenie dat</button>
        <button class="tab" data-tab="jazdy" aria-selected="false">Jazdy vozidiel</button>
        <button class="tab" data-tab="material" aria-selected="false">Pohyby materialu</button>
        <button class="tab" data-tab="pokrocila" aria-selected="false">Pokrocila analytika</button>
      </div>
    </div>
  </div>

  <main>
    __UNDERSTANDING_SECTION__
    __JAZDY_SECTION__
    __MATERIAL_SECTION__
    __ADVANCED_SECTION__
    <div class="footer-note">Vystup je samostatny HTML export. Pri regeneracii sa prepise zo skriptu `scripts/02_build_dashboard.py`.</div>
  </main>

  <div id="chartTooltip" class="chart-tooltip" aria-hidden="true">
    <div class="chart-tooltip-label"></div>
    <div class="chart-tooltip-value"></div>
  </div>

  <script id="dashboard-data" type="application/json">__JSON_BLOB__</script>
  <script>
    const dashboard = JSON.parse(document.getElementById("dashboard-data").textContent);
    const chartTooltip = document.getElementById("chartTooltip");
    const chartTooltipLabel = chartTooltip.querySelector(".chart-tooltip-label");
    const chartTooltipValue = chartTooltip.querySelector(".chart-tooltip-value");
    const palette = {
      accent1: "#00d4ff",
      accent2: "#ff7a45",
      accent3: "#71f3ab",
      accent4: "#ffd166",
      text: "#ebf1fb",
      textSoft: "#9db1ca",
      grid: "rgba(88, 118, 165, 0.22)",
      panel: "#13213a",
      hole: "#0d182b"
    };

    let activeTab = "pochopenie";

    function formatNumber(value, digits = 0) {
      return new Intl.NumberFormat("sk-SK", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits
      }).format(value);
    }

    function formatCompact(value) {
      const abs = Math.abs(value);
      if (abs >= 1_000_000_000) {
        return formatNumber(value / 1_000_000_000, 1) + "B";
      }
      if (abs >= 1_000_000) {
        return formatNumber(value / 1_000_000, 1) + "M";
      }
      if (abs >= 1_000) {
        return formatNumber(value / 1_000, 1) + "K";
      }
      return formatNumber(value, 0);
    }

    function prepCanvas(id) {
      const canvas = document.getElementById(id);
      if (!canvas) return null;

      const rect = canvas.getBoundingClientRect();
      if (!rect.width) return null;

      const height = Number(canvas.getAttribute("height") || 220);
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.height = height + "px";
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, rect.width, height);
      return { canvas, ctx, width: rect.width, height };
    }

    function fillRoundedRect(ctx, x, y, width, height, radius) {
      const r = Math.min(radius, width / 2, height / 2);
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + width, y, x + width, y + height, r);
      ctx.arcTo(x + width, y + height, x, y + height, r);
      ctx.arcTo(x, y + height, x, y, r);
      ctx.arcTo(x, y, x + width, y, r);
      ctx.closePath();
      ctx.fill();
    }

    function hideChartTooltip() {
      chartTooltip.classList.remove("visible");
      chartTooltip.setAttribute("aria-hidden", "true");
    }

    function positionChartTooltip(event) {
      const offset = 16;
      const rect = chartTooltip.getBoundingClientRect();
      let left = event.clientX + offset;
      let top = event.clientY + offset;

      if (left + rect.width > window.innerWidth - 12) {
        left = event.clientX - rect.width - offset;
      }
      if (top + rect.height > window.innerHeight - 12) {
        top = event.clientY - rect.height - offset;
      }

      chartTooltip.style.left = Math.max(12, left) + "px";
      chartTooltip.style.top = Math.max(12, top) + "px";
    }

    function showChartTooltip(event, hitBox) {
      chartTooltipLabel.textContent = hitBox.label;
      chartTooltipValue.textContent = hitBox.tooltipValue;
      positionChartTooltip(event);
      chartTooltip.classList.add("visible");
      chartTooltip.setAttribute("aria-hidden", "false");
    }

    function bindChartHover(canvas, hitBoxes) {
      canvas.__chartHitBoxes = hitBoxes;

      if (canvas.dataset.hoverBound === "true") {
        return;
      }

      canvas.dataset.hoverBound = "true";
      canvas.addEventListener("mousemove", (event) => {
        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        const hitBox = (canvas.__chartHitBoxes || []).find(
          (item) =>
            x >= item.x
            && x <= item.x + item.width
            && y >= item.y
            && y <= item.y + item.height
        );

        canvas.style.cursor = hitBox ? "pointer" : "default";
        if (!hitBox) {
          hideChartTooltip();
          return;
        }

        showChartTooltip(event, hitBox);
      });

      canvas.addEventListener("mouseleave", () => {
        canvas.style.cursor = "default";
        hideChartTooltip();
      });
    }

    function drawBarChart(
      id,
      items,
      color,
      formatter = (value) => formatNumber(value, 0),
      options = {}
    ) {
      const setup = prepCanvas(id);
      if (!setup || !items.length) return;

      const { canvas, ctx, width, height } = setup;
      const pad = { top: 20, right: 14, bottom: 40, left: 54 };
      const chartWidth = width - pad.left - pad.right;
      const chartHeight = height - pad.top - pad.bottom;
      const maxValue = Math.max(...items.map((item) => Number(item.value))) * 1.12 || 1;
      const step = chartWidth / items.length;
      const barWidth = Math.max(10, Math.min(28, step * 0.62));
      const hitBoxes = [];

      ctx.strokeStyle = palette.grid;
      ctx.fillStyle = palette.textSoft;
      ctx.font = "10px DM Mono";
      ctx.textAlign = "right";

      for (let i = 0; i <= 4; i += 1) {
        const y = pad.top + chartHeight - (chartHeight * i) / 4;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(width - pad.right, y);
        ctx.stroke();
        ctx.fillText(formatter((maxValue * i) / 4), pad.left - 6, y + 3);
      }

      items.forEach((item, index) => {
        const value = Number(item.value);
        const barHeight = (value / maxValue) * chartHeight;
        const x = pad.left + index * step + (step - barWidth) / 2;
        const y = pad.top + chartHeight - barHeight;
        const visibleHeight = Math.max(barHeight, 2);

        const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
        gradient.addColorStop(0, color);
        gradient.addColorStop(1, color + "33");
        ctx.fillStyle = gradient;
        fillRoundedRect(ctx, x, y, barWidth, visibleHeight, 5);

        if (options.tooltip) {
          const tooltipFormatter = options.tooltipFormatter || formatter;
          hitBoxes.push({
            x,
            y,
            width: barWidth,
            height: visibleHeight,
            label: item.label,
            tooltipValue: tooltipFormatter(value),
          });
        }

        const showLabel = items.length <= 14 || index % 2 === 0;
        if (showLabel) {
          ctx.fillStyle = palette.textSoft;
          ctx.font = "10px DM Mono";
          ctx.textAlign = "center";
          ctx.fillText(item.label, x + barWidth / 2, height - 14);
        }
      });

      if (options.tooltip) {
        bindChartHover(canvas, hitBoxes);
      }
    }

    function drawHorizontalBars(
      id,
      items,
      color,
      formatter = (value) => formatNumber(value, 0),
      options = {}
    ) {
      const setup = prepCanvas(id);
      if (!setup || !items.length) return;

      const { canvas, ctx, width, height } = setup;
      const pad = { top: 16, right: 90, bottom: 12, left: 88 };
      const chartWidth = width - pad.left - pad.right;
      const chartHeight = height - pad.top - pad.bottom;
      const maxValue = Math.max(...items.map((item) => Number(item.value))) * 1.08 || 1;
      const rowHeight = chartHeight / items.length;
      const barHeight = Math.max(12, rowHeight * 0.54);
      const hitBoxes = [];

      items.forEach((item, index) => {
        const value = Number(item.value);
        const y = pad.top + index * rowHeight + (rowHeight - barHeight) / 2;
        const barWidth = Math.max(4, (value / maxValue) * chartWidth);

        ctx.fillStyle = "rgba(88, 118, 165, 0.10)";
        fillRoundedRect(ctx, pad.left, y, chartWidth, barHeight, 6);

        const gradient = ctx.createLinearGradient(pad.left, 0, pad.left + barWidth, 0);
        gradient.addColorStop(0, color + "bb");
        gradient.addColorStop(1, color);
        ctx.fillStyle = gradient;
        fillRoundedRect(ctx, pad.left, y, barWidth, barHeight, 6);

        ctx.fillStyle = palette.textSoft;
        ctx.font = "10px DM Mono";
        ctx.textAlign = "right";
        ctx.fillText(item.label, pad.left - 8, y + barHeight / 2 + 4);

        ctx.fillStyle = palette.text;
        ctx.textAlign = "left";
        ctx.fillText(formatter(value), pad.left + barWidth + 8, y + barHeight / 2 + 4);

        if (options.tooltip) {
          const tooltipFormatter = options.tooltipFormatter || formatter;
          hitBoxes.push({
            x: pad.left,
            y,
            width: barWidth,
            height: barHeight,
            label: item.label,
            tooltipValue: tooltipFormatter(value),
          });
        }
      });

      if (options.tooltip) {
        bindChartHover(canvas, hitBoxes);
      }
    }

    function drawDonutChart(id, items, colors, formatter = (value) => formatNumber(value, 0)) {
      const setup = prepCanvas(id);
      if (!setup || !items.length) return;

      const { ctx, width, height } = setup;
      const total = items.reduce((sum, item) => sum + Number(item.value), 0) || 1;
      const compact = width < 420;
      const centerX = compact ? width / 2 : width * 0.28;
      const centerY = compact ? height * 0.36 : height / 2;
      const radius = Math.min(compact ? width * 0.18 : width * 0.15, height * 0.28);
      const innerRadius = radius * 0.58;
      let startAngle = -Math.PI / 2;

      items.forEach((item, index) => {
        const slice = (Number(item.value) / total) * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, startAngle + slice);
        ctx.closePath();
        ctx.fillStyle = colors[index % colors.length];
        ctx.fill();
        startAngle += slice;
      });

      ctx.beginPath();
      ctx.arc(centerX, centerY, innerRadius, 0, Math.PI * 2);
      ctx.fillStyle = palette.hole;
      ctx.fill();

      ctx.fillStyle = palette.textSoft;
      ctx.font = "10px DM Mono";
      ctx.textAlign = "center";
      ctx.fillText("TOTAL", centerX, centerY - 2);
      ctx.fillStyle = palette.text;
      ctx.font = "bold 18px Syne";
      ctx.fillText(formatter(total), centerX, centerY + 20);

      const legendX = compact ? 24 : width * 0.56;
      const legendStartY = compact ? height * 0.62 : height * 0.28;

      items.forEach((item, index) => {
        const y = legendStartY + index * 32;
        ctx.fillStyle = colors[index % colors.length];
        ctx.beginPath();
        ctx.arc(legendX, y, 5, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = palette.text;
        ctx.font = "12px DM Sans";
        ctx.textAlign = "left";
        ctx.fillText(item.label, legendX + 12, y + 4);

        ctx.fillStyle = palette.textSoft;
        ctx.font = "10px DM Mono";
        const pct = Math.round((Number(item.value) / total) * 100);
        ctx.fillText(formatter(Number(item.value)) + " | " + pct + "%", legendX + 12, y + 18);
      });
    }

    function drawTripsCharts() {
      drawBarChart(
        "chartMonthlyTrips",
        dashboard.jazdy.charts.jazdy_podla_mesiaca,
        palette.accent1,
        (value) => formatNumber(value, 0),
        { tooltip: true }
      );
      drawBarChart(
        "chartWeekdayTrips",
        dashboard.jazdy.charts.jazdy_podla_dna,
        palette.accent4,
        (value) => formatNumber(value, 0),
        { tooltip: true }
      );
      drawDonutChart(
        "chartTripDistance",
        dashboard.jazdy.charts.rozdelenie_podla_vzdialenosti,
        [palette.accent2, palette.accent1, palette.accent3, palette.accent4, "#9f7aea"]
      );
      drawHorizontalBars(
        "chartTopVehicles",
        dashboard.jazdy.charts.top_vozidla_podla_poctu_jazd,
        palette.accent1,
        (value) => formatNumber(value, 0),
        { tooltip: true }
      );
    }

    function drawMaterialCharts() {
      drawBarChart("chartMaterialMoves", dashboard.material.charts.pohyby_podla_mesiaca, palette.accent3);
      drawBarChart(
        "chartMaterialQty",
        dashboard.material.charts.mnozstvo_podla_mesiaca,
        palette.accent4,
        (value) => formatCompact(value)
      );
      drawDonutChart(
        "chartAbcSegments",
        dashboard.material.charts.abc_segmenty,
        [palette.accent1, palette.accent4, palette.accent3]
      );
      drawHorizontalBars("chartTopPrefixes", dashboard.material.charts.top_prefixy_podla_pohybov, palette.accent3);
    }

    function drawAdvancedCharts() {
      const vehicleItems = dashboard.pokrocilejsia_analytika.jazdy.top_vehicle_shares.map((item) => ({
        label: item.vehicle_id,
        value: Number(item.inefficient_share_pct)
      }));
      const abcQtyItems = dashboard.pokrocilejsia_analytika.material.abc_summary.map((item) => ({
        label: item.abc_segment,
        value: Number(item.quantity_share_pct)
      }));

      drawHorizontalBars(
        "chartInefficientVehicles",
        vehicleItems,
        palette.accent2,
        (value) => formatNumber(value, 1) + "%"
      );
      drawHorizontalBars(
        "chartAbcQtyShare",
        abcQtyItems,
        palette.accent4,
        (value) => formatNumber(value, 1) + "%"
      );
    }

    function drawActiveTab() {
      hideChartTooltip();
      if (activeTab === "jazdy") {
        drawTripsCharts();
      } else if (activeTab === "material") {
        drawMaterialCharts();
      } else if (activeTab === "pokrocila") {
        drawAdvancedCharts();
      }
    }

    function showTab(name) {
      activeTab = name;
      document.querySelectorAll(".section").forEach((section) => {
        section.classList.toggle("active", section.id === "tab-" + name);
      });

      document.querySelectorAll(".tab").forEach((button) => {
        const isActive = button.dataset.tab === name;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-selected", isActive ? "true" : "false");
      });

      requestAnimationFrame(drawActiveTab);
    }

    document.querySelectorAll(".tab").forEach((button) => {
      button.addEventListener("click", () => showTab(button.dataset.tab));
    });

    let resizeTimer = null;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(drawActiveTab, 120);
    });

    window.addEventListener("DOMContentLoaded", () => {
      drawActiveTab();
    });
  </script>
</body>
</html>
"""

    html = template
    html = html.replace("__HEADER_SUB__", escape(header_sub))
    html = html.replace("__HEADER_DATASET_CARDS__", header_cards)
    html = html.replace("__UNDERSTANDING_SECTION__", understanding_section)
    html = html.replace("__JAZDY_SECTION__", jazdy_section)
    html = html.replace("__MATERIAL_SECTION__", material_section)
    html = html.replace("__ADVANCED_SECTION__", advanced_section)
    html = html.replace("__JSON_BLOB__", json_blob)
    return html


def main() -> None:
    VIS_DIR.mkdir(parents=True, exist_ok=True)

    jazdy = load_jazdy_dataset(JAZDY_INPUT)
    material = load_material_dataset(MATERIAL_INPUT)

    dashboard = build_dashboard_data(jazdy, material)

    html = build_html(dashboard)
    HTML_OUTPUT.write_text(html, encoding="utf-8")

    print("Built HTML dashboard:")
    print(f"  source jazdy: {JAZDY_INPUT}")
    print(f"  source material: {MATERIAL_INPUT}")
    print(f"  output html: {HTML_OUTPUT}")


if __name__ == "__main__":
    main()
