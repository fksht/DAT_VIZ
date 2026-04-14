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

TABLEAU_RIDE_CATEGORY_ORDER = [
    "Žiadna jazda (0m)",
    "Parkovanie (<100m)",
    "Krátka (100m-1km)",
    "Mestská (1-5km)",
    "Regionálna (5-50km)",
    "Diaľková (>50km)",
]

RIDES_MONTH_LABELS_SHORT = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "Maj",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Okt",
    11: "Nov",
    12: "Dec",
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
        "description": "Odvodene priznaky pre near-zero heuristiku, Tableau validitu jazdy a vzdialenostne kategorie.",
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


def classify_tableau_ride_category(distance_m: float) -> str:
    if pd.isna(distance_m):
        return "Neznáme"
    if distance_m == 0:
        return "Žiadna jazda (0m)"
    if distance_m < 0.1:
        return "Parkovanie (<100m)"
    if distance_m < 1:
        return "Krátka (100m-1km)"
    if distance_m < 5:
        return "Mestská (1-5km)"
    if distance_m < 50:
        return "Regionálna (5-50km)"
    return "Diaľková (>50km)"


def format_raw_coordinate(value: object) -> str:
    if pd.isna(value):
        return "?"

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)

    if numeric.is_integer():
        return str(int(numeric))
    return str(value)


def json_number_or_none(value: object) -> float | int | None:
    if pd.isna(value):
        return None
    numeric = float(value)
    if numeric.is_integer():
        return int(numeric)
    return numeric


def build_tableau_route_label(row: pd.Series) -> str:
    return (
        f"{format_raw_coordinate(row['EW_START'])},{format_raw_coordinate(row['EL_START'])} "
        f"→ {format_raw_coordinate(row['EW_END'])},{format_raw_coordinate(row['EL_END'])}"
    )


def build_normalized_route_label(row: pd.Series) -> str:
    if pd.isna(row["start_lat"]) or pd.isna(row["start_lon"]) or pd.isna(row["end_lat"]) or pd.isna(row["end_lon"]):
        return ""
    return (
        f"{row['start_lat']:.5f},{row['start_lon']:.5f} "
        f"→ {row['end_lat']:.5f},{row['end_lon']:.5f}"
    )


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
    tableau_lat_start = pd.to_numeric(df["EW_START"], errors="coerce") / 1_000_000
    tableau_lon_start = pd.to_numeric(df["EL_START"], errors="coerce") / 1_000_000
    tableau_lat_end = pd.to_numeric(df["EW_END"], errors="coerce") / 1_000_000
    tableau_lon_end = pd.to_numeric(df["EL_END"], errors="coerce") / 1_000_000
    distance_m = pd.to_numeric(df["DIST_START_END_M"], errors="coerce") / 1e9
    distance_km = distance_m / 1000

    coord_valid = (
        start_lat.between(47, 51)
        & start_lon.between(12, 23)
        & end_lat.between(47, 51)
        & end_lon.between(12, 23)
    )
    tableau_valid_trip = (
        tableau_lat_start.between(47, 51)
        & tableau_lon_start.between(12, 23)
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
            "distance_m": distance_m,
            "distance_km": distance_km,
            "ew_start_raw": pd.to_numeric(df["EW_START"], errors="coerce"),
            "el_start_raw": pd.to_numeric(df["EL_START"], errors="coerce"),
            "start_lat": start_lat,
            "start_lon": start_lon,
            "end_lat": end_lat,
            "end_lon": end_lon,
            "coord_valid": coord_valid,
            "tableau_lat_start": tableau_lat_start,
            "tableau_lon_start": tableau_lon_start,
            "tableau_lat_end": tableau_lat_end,
            "tableau_lon_end": tableau_lon_end,
            "tableau_valid_trip": tableau_valid_trip,
            "ride_category_tableau": distance_m.apply(classify_tableau_ride_category),
            "trasa_tableau": df.apply(build_tableau_route_label, axis=1),
        }
    )

    cleaned.loc[~cleaned["coord_valid"], ["start_lat", "start_lon", "end_lat", "end_lon"]] = np.nan
    cleaned["route_summary_label"] = cleaned.apply(build_normalized_route_label, axis=1)
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


def rides_month_label_short(value: str) -> str:
    _, month = value.split("-")
    return RIDES_MONTH_LABELS_SHORT.get(int(month), month)


def classify_prefix(row: pd.Series) -> str:
    if float(row["quantity_share_pct"]) >= 10:
        return "objemovo dominantny"
    if float(row["movement_share_pct"]) >= 5:
        return "frekventovany"
    if int(row["unique_material_count"]) >= 20:
        return "sirsie portfolio"
    return "stabilny"


def classify_material_segment(row: pd.Series) -> tuple[str, str]:
    quantity_share_pct = float(row["quantity_share_pct"])
    movement_share_pct = float(row["movement_share_pct"])
    active_months = int(row["active_months"])
    peak_month_share_pct = float(row["peak_month_share_pct"])

    if quantity_share_pct >= 5 or movement_share_pct >= 7:
        if quantity_share_pct >= 5:
            return "Kritické", "nesu aspon 5 % celkoveho objemu"
        return "Kritické", "patria medzi frekvencne najvytazenejsie prefixy"

    if active_months < 12 or peak_month_share_pct >= 35:
        if active_months < 12:
            return "Rizikové", "aktivita je kratka alebo epizodicka"
        return "Rizikové", "aktivita je silno koncentrovana do jedneho mesiaca"

    if active_months >= 30 and movement_share_pct >= 1 and peak_month_share_pct < 10:
        return "Stabilné", "maju pravidelnu aktivitu napriec obdobiami"

    return "Pomalyobrátkové", "maju nizku frekvenciu aj nizky objem"


def compute_advanced_ride_analytics(jazdy: pd.DataFrame, trips_per_vehicle: pd.DataFrame) -> dict:
    # This goes beyond descriptive reporting because it ranks manual-review priority using a transparent,
    # rule-based score instead of only listing counts. The result is heuristic and explicitly not a proof of waste.
    short_trip_counts = (
        jazdy.groupby("vehicle_id", as_index=False)
        .agg(short_trip_count=("short_trip", "sum"))
    )
    ride_review = trips_per_vehicle.merge(short_trip_counts, on="vehicle_id", how="left")
    ride_review["short_trip_count"] = ride_review["short_trip_count"].fillna(0).astype(int)
    ride_review["short_share_pct"] = (
        ride_review["short_trip_count"] / ride_review["trip_count"] * 100
    ).round(1)
    ride_review["review_score"] = (
        ride_review["inefficient_share_pct"] * 0.5
        + ride_review["near_zero_share_pct"] * 0.3
        + ride_review["short_share_pct"] * 0.2
    ).round(1)
    ride_review["priority_band"] = np.select(
        [
            ride_review["review_score"] >= 25,
            ride_review["review_score"] >= 20,
        ],
        [
            "Vysoká priorita",
            "Stredná priorita",
        ],
        default="Nižšia priorita",
    )
    ride_review = ride_review.sort_values(
        ["review_score", "inefficient_share_pct", "trip_count", "vehicle_id"],
        ascending=[False, False, False, True],
    )

    total_flagged = int(jazdy["potentially_inefficient_trip"].sum())
    high_priority = ride_review.loc[ride_review["review_score"] >= 25].copy()
    flagged_in_high_priority = int(high_priority["inefficient_trip_count"].sum())
    flagged_focus_share_pct = (
        flagged_in_high_priority / total_flagged * 100 if total_flagged else 0
    )
    top_vehicle = ride_review.iloc[0]

    return {
        "question": "Ktoré vozidlá koncentrujú najvyšší podiel potenciálne neefektívnych a nízkohodnotných jázd?",
        "method_title": "Heuristické prioritizačné skóre pre manuálnu kontrolu",
        "method_points": [
            "Jazda je označená ako potenciálne neefektívna, ak trvá aspoň 30 minút a posun je menší ako 0,5 km.",
            "Na úrovni vozidla sa počíta skóre = 50 % podiel označených jázd + 30 % near-zero podiel + 20 % podiel krátkych jázd do 5 km.",
            "Skóre je len proxy pre manuálnu kontrolu. Neznamená dokázanú neefektivitu ani finančnú škodu.",
        ],
        "summary_cards": [
            {
                "label": "Označené jazdy",
                "value": total_flagged,
                "sub": "signál na manuálnu kontrolu",
                "format": "int",
            },
            {
                "label": "Vozidlá s vysokou prioritou",
                "value": int(len(high_priority)),
                "sub": "skóre aspoň 25 bodov",
                "format": "int",
            },
            {
                "label": "Koncentrácia signálu",
                "value": round(flagged_focus_share_pct, 1),
                "sub": "podiel označených jázd v top prioritných vozidlách",
                "format": "pct1",
            },
        ],
        "chart": [
            {
                "label": row.vehicle_id,
                "value": float(row.review_score),
            }
            for row in ride_review.head(8).itertuples(index=False)
        ],
        "table": [
            {
                "vehicle_id": row.vehicle_id,
                "trip_count": int(row.trip_count),
                "inefficient_trip_count": int(row.inefficient_trip_count),
                "inefficient_share_pct": float(row.inefficient_share_pct),
                "near_zero_share_pct": float(row.near_zero_share_pct),
                "short_share_pct": float(row.short_share_pct),
                "review_score": float(row.review_score),
                "priority_band": row.priority_band,
            }
            for row in ride_review.head(8).itertuples(index=False)
        ],
        "result_text": (
            f"Najvyššie skóre má vozidlo {top_vehicle.vehicle_id} ({top_vehicle.review_score:.1f}). "
            f"Vozidlá s vysokou prioritou držia {flagged_focus_share_pct:.1f} % všetkých označených jázd."
        ),
        "interpretation": (
            f"Manuálnu kontrolu sa oplatí začať pri vozidle {top_vehicle.vehicle_id}, pretože kombinuje vysoký podiel "
            f"označených jázd s vysokou koncentráciou near-zero a krátkych presunov. Tento výstup je vhodný ako "
            f"obhájiteľná priorita pre dispečing alebo fleet management."
        ),
        "recommendations": [
            "Najprv preveriť top vozidlá s vysokou prioritou a porovnať ich s pracovným režimom alebo typom vozidla.",
            "Near-zero a krátke jazdy čítať ako prevádzkový signál, nie ako automatický dôkaz neefektivity.",
            "Ak sa tie isté vozidlá opakujú aj v ďalších obdobiach, skóre sa dá použiť ako jednoduchý monitoring proxy.",
        ],
    }


def compute_advanced_material_analytics(material: pd.DataFrame, prefix_summary: pd.DataFrame) -> dict:
    # This is advanced analytics because it converts raw movement/quantity history into explicit operational classes.
    # The rules are transparent and interpretable, which is more defensible here than a black-box clustering model.
    segmented = prefix_summary.copy()
    segment_meta = segmented.apply(classify_material_segment, axis=1, result_type="expand")
    segmented["segment"] = segment_meta[0]
    segmented["segment_reason"] = segment_meta[1]

    segment_order = ["Kritické", "Stabilné", "Rizikové", "Pomalyobrátkové"]
    segmented["segment_order"] = segmented["segment"].map({name: idx for idx, name in enumerate(segment_order)})

    segment_summary = (
        segmented.groupby(["segment", "segment_order"], as_index=False)
        .agg(
            prefix_count=("material_prefix", "size"),
            movement_count=("movement_count", "sum"),
            quantity_share_pct=("quantity_share_pct", "sum"),
        )
        .sort_values("segment_order")
    )
    segment_summary["movement_share_pct"] = (
        segment_summary["movement_count"] / len(material) * 100
    ).round(1)

    critical_prefix = segmented.sort_values(
        ["quantity_share_pct", "movement_share_pct", "material_prefix"],
        ascending=[False, False, True],
    ).iloc[0]
    risky_candidates = segmented.loc[segmented["segment"] == "Rizikové"].copy()
    risky_prefix = (
        risky_candidates.sort_values(
            ["peak_month_share_pct", "movement_count", "material_prefix"],
            ascending=[False, False, True],
        ).iloc[0]
        if not risky_candidates.empty
        else None
    )

    priority_candidates = segmented.loc[segmented["segment"].isin(["Kritické", "Rizikové"])].copy()
    if priority_candidates.empty:
        priority_candidates = segmented.copy()
    priority_candidates["priority_order"] = priority_candidates["segment"].map(
        {"Kritické": 0, "Rizikové": 1}
    ).fillna(2)
    priority_prefixes = priority_candidates.sort_values(
        ["priority_order", "quantity_share_pct", "peak_month_share_pct", "movement_count"],
        ascending=[True, False, False, False],
    ).head(10)

    critical_summary = segment_summary.loc[segment_summary["segment"] == "Kritické"].iloc[0]
    risky_summary_rows = segment_summary.loc[segment_summary["segment"] == "Rizikové"]
    risky_summary = (
        risky_summary_rows.iloc[0]
        if not risky_summary_rows.empty
        else pd.Series({"prefix_count": 0, "quantity_share_pct": 0.0, "movement_share_pct": 0.0})
    )
    risky_interpretation = (
        f"zatiaľ čo prefix {risky_prefix.material_prefix} reprezentuje bursty alebo krátku históriu a zaslúži si "
        f"samostatný monitoring."
        if risky_prefix is not None
        else "rizikový segment je v tomto exporte prázdny, čo znamená, že pravidlá nenašli epizodickú skupinu vyžadujúcu samostatný monitoring."
    )

    return {
        "question": "Ktoré materiálové prefixy sú z pohľadu prevádzky stabilné, kritické, rizikové alebo pomalyobrátkové?",
        "method_title": "Transparentná segmentácia prefixov podľa objemu, frekvencie a časovej koncentrácie",
        "method_points": [
            "Kritické prefixy nesú aspoň 5 % celkového objemu alebo patria medzi frekvenčne najvyťaženejšie prefixy nad 7 % pohybov.",
            "Rizikové prefixy sú tie, ktoré majú krátku históriu do 12 aktívnych mesiacov alebo viac ako 35 % svojej aktivity v jednom mesiaci.",
            "Stabilné prefixy sa hýbu pravidelne aspoň 30 mesiacov, držia aspoň 1 % pohybov a ich aktivita nie je koncentrovaná do jedného mesiaca. Ostatné sú pomalyobrátkové.",
        ],
        "summary_cards": [
            {
                "label": "Kritické prefixy",
                "value": int(critical_summary.prefix_count),
                "sub": "nesú najväčší operačný dopad",
                "format": "int",
            },
            {
                "label": "Podiel kritického objemu",
                "value": round(float(critical_summary.quantity_share_pct), 1),
                "sub": "percent z celkoveho mnozstva",
                "format": "pct1",
            },
            {
                "label": "Rizikové prefixy",
                "value": int(risky_summary.prefix_count),
                "sub": "epizodická alebo bursty aktivita",
                "format": "int",
            },
        ],
        "chart": [
            {
                "label": row.segment,
                "value": float(row.quantity_share_pct),
            }
            for row in segment_summary.itertuples(index=False)
        ],
        "segment_table": [
            {
                "segment": row.segment,
                "prefix_count": int(row.prefix_count),
                "movement_share_pct": float(row.movement_share_pct),
                "quantity_share_pct": float(row.quantity_share_pct),
            }
            for row in segment_summary.itertuples(index=False)
        ],
        "priority_table": [
            {
                "material_prefix": row.material_prefix,
                "segment": row.segment,
                "movement_share_pct": float(row.movement_share_pct),
                "quantity_share_pct": float(row.quantity_share_pct),
                "active_months": int(row.active_months),
                "peak_month_share_pct": float(row.peak_month_share_pct),
                "reason": row.segment_reason,
            }
            for row in priority_prefixes.itertuples(index=False)
        ],
        "result_text": (
            f"Kritická skupina má iba {int(critical_summary.prefix_count)} prefixov, ale nesie "
            f"{critical_summary.quantity_share_pct:.1f} % celkového objemu. Najväčší objemový dopad má "
            f"{critical_prefix.material_prefix} ({critical_prefix.quantity_share_pct:.1f} %)."
        ),
        "interpretation": (
            f"Segmentácia ukazuje, že najväčšie prevádzkové riziko je sústredené v malej skupine kritických prefixov, "
            f"{risky_interpretation} Toto je vhodnejsie a obhajitelnejsie ako netransparentny clustering."
        ),
        "recommendations": [
            "Kritické prefixy sledovať oddelene, lebo nesú väčšinu objemu alebo frekvencie a majú najväčší dopad na prevádzku.",
            "Rizikové prefixy porovnať s plánom nákupu alebo jednorazovými projektmi, aby sa odlíšila sezónnosť od abnormality.",
            "Pomalyobrátkové prefixy použiť ako kandidáta na revíziu sortimentu alebo minimálnych zásob.",
        ],
    }


def build_dashboard_data(jazdy: pd.DataFrame, material: pd.DataFrame) -> dict:
    jazdy["trip_date"] = pd.to_datetime(jazdy["trip_date"])
    material["movement_date"] = pd.to_datetime(material["movement_date"])

    valid_jazdy = jazdy.loc[~jazdy["near_zero_trip"]].copy()
    tableau_valid_jazdy = jazdy.loc[jazdy["tableau_valid_trip"]].copy()

    trips_per_vehicle = (
        jazdy.groupby("vehicle_id", as_index=False)
        .agg(
            trip_count=("vehicle_id", "size"),
            valid_trip_count=("tableau_valid_trip", "sum"),
            near_zero_count=("near_zero_trip", "sum"),
            inefficient_trip_count=("potentially_inefficient_trip", "sum"),
            weekend_trip_count=("weekend", "sum"),
            total_distance_km=("distance_km", "sum"),
            avg_trip_distance_km=("distance_km", "mean"),
        )
        .sort_values(["trip_count", "vehicle_id"], ascending=[False, True])
    )

    category_priority = {name: index for index, name in enumerate(TABLEAU_RIDE_CATEGORY_ORDER)}
    dominant_vehicle_category = (
        jazdy.groupby(["vehicle_id", "ride_category_tableau"], as_index=False)
        .agg(category_trip_count=("vehicle_id", "size"))
        .assign(category_order=lambda df: df["ride_category_tableau"].map(category_priority).fillna(999))
        .sort_values(
            ["vehicle_id", "category_trip_count", "category_order", "ride_category_tableau"],
            ascending=[True, False, True, True],
        )
        .drop_duplicates("vehicle_id")
        .rename(columns={"ride_category_tableau": "dominant_category"})
        [["vehicle_id", "dominant_category"]]
    )

    trips_per_vehicle = trips_per_vehicle.merge(dominant_vehicle_category, on="vehicle_id", how="left")
    trips_per_vehicle["valid_share_pct"] = (
        trips_per_vehicle["valid_trip_count"] / trips_per_vehicle["trip_count"] * 100
    ).round(1)
    trips_per_vehicle["trip_share_pct"] = (trips_per_vehicle["trip_count"] / len(jazdy) * 100).round(1)
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

    rides_categories = (
        jazdy["ride_category_tableau"]
        .value_counts()
        .reindex(TABLEAU_RIDE_CATEGORY_ORDER, fill_value=0)
        .rename_axis("ride_category")
        .reset_index(name="trip_count")
    )
    top_routes = (
        jazdy.loc[
            jazdy["tableau_valid_trip"]
            & jazdy["route_summary_label"].ne("")
            & jazdy["distance_m"].gt(0)
        ]
        .groupby(["route_summary_label", "trasa_tableau"], as_index=False)
        .agg(
            record_count=("vehicle_id", "size"),
            avg_distance_km=("distance_km", "mean"),
        )
        .sort_values(
            ["record_count", "avg_distance_km", "route_summary_label"],
            ascending=[False, False, True],
        )
        .head(8)
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
    prefix_activity = (
        material.groupby("material_prefix", as_index=False)
        .agg(
            active_months=("year_month", "nunique"),
            zero_qty_count=("zero_quantity_record", "sum"),
        )
    )
    prefix_peak_month = (
        material.groupby(["material_prefix", "year_month"], as_index=False)
        .agg(month_move_count=("material_number", "size"))
        .groupby("material_prefix", as_index=False)
        .agg(peak_month_count=("month_move_count", "max"))
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
    prefix_summary = prefix_summary.merge(prefix_activity, on="material_prefix", how="left")
    prefix_summary = prefix_summary.merge(prefix_peak_month, on="material_prefix", how="left")
    prefix_summary["zero_qty_share_pct"] = (
        prefix_summary["zero_qty_count"] / prefix_summary["movement_count"] * 100
    ).round(2)
    prefix_summary["peak_month_share_pct"] = (
        prefix_summary["peak_month_count"] / prefix_summary["movement_count"] * 100
    ).round(1)
    prefix_summary["profile"] = prefix_summary.apply(classify_prefix, axis=1)

    abc_summary["movement_share_pct"] = (abc_summary["movement_count"] / len(material) * 100).round(1)
    abc_summary["quantity_share_pct"] = (
        abc_summary["total_quantity"] / total_material_quantity * 100
    ).round(1)

    advanced_ride_analytics = compute_advanced_ride_analytics(jazdy, trips_per_vehicle)
    advanced_material_analytics = compute_advanced_material_analytics(material, prefix_summary)

    most_used_vehicle = trips_per_vehicle.iloc[0]
    least_used_vehicle = trips_per_vehicle.iloc[-1]
    most_active_weekday = rides_weekday.sort_values("trip_count", ascending=False).iloc[0]
    highest_valid_share_vehicle = trips_per_vehicle.sort_values(
        ["valid_share_pct", "trip_count", "vehicle_id"],
        ascending=[False, False, True],
    ).iloc[0]
    top_ride_category = rides_categories.sort_values(
        ["trip_count", "ride_category"],
        ascending=[False, True],
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
                    "Tableau validita jazdy je viazana na startove suradnice po prepocte EW_START / 1000000 a EL_START / 1000000.",
                    "Workbook ma aj priestorove pohlady, ale HTML ich sumarizuje len textovo a cez tabulku tras podla suradnic.",
                ],
                "answerable": [
                    "vytazenost vozidiel a rozlozenie jazd v case",
                    "porovnanie mesiacov, dni v tyzdni a Tableau kategorii jazd",
                    "odhad dopadu filtra Zobrazit iba validne jazdy",
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
                "Pocet jazd": int(len(jazdy)),
                "Pocet vozidiel": int(jazdy["vehicle_id"].nunique()),
                "Priemer jazdy na vozidlo": int(round(len(jazdy) / jazdy["vehicle_id"].nunique(), 0)),
                "Validne jazdy Tableau": int(jazdy["tableau_valid_trip"].sum()),
                "Nevalidne jazdy Tableau": int((~jazdy["tableau_valid_trip"]).sum()),
                "Ziadna jazda 0m": int((jazdy["ride_category_tableau"] == "Žiadna jazda (0m)").sum()),
            },
            "totals": {
                "valid_distance_km": round(float(valid_jazdy["distance_km"].sum()), 2),
                "avg_trips_per_vehicle": round(float(len(jazdy) / jazdy["vehicle_id"].nunique()), 1),
                "near_zero_share_pct": round(float(jazdy["near_zero_trip"].mean() * 100), 1),
                "short_trip_count": int(jazdy["short_trip"].sum()),
                "weekend_trip_count": int(jazdy["weekend"].sum()),
                "tableau_valid_share_pct": round(float(jazdy["tableau_valid_trip"].mean() * 100), 1),
                "tableau_invalid_share_pct": round(float((~jazdy["tableau_valid_trip"]).mean() * 100), 1),
                "route_summary_ready_count": int(jazdy["route_summary_label"].ne("").sum()),
            },
            "tableau": {
                "parameter_name": "Zobraziť iba validné jazdy",
                "parameter_default": True,
                "validity_logic": "LAT_START medzi 47 a 51 a LON_START medzi 12 a 23",
                "worksheets": [
                    "Jazdy podľa dňa",
                    "KPI - Počet jázd",
                    "KPI - Počet vozidiel",
                    "KPI - Priem. jazdy",
                    "Kategórie jázd",
                    "Mapa hustoty jázd",
                    "Mapa jázd",
                    "Trasy",
                    "Vyťaženosť vozidiel",
                    "Vývoj jázd v čase",
                ],
            },
            "charts": {
                "jazdy_podla_mesiaca": [
                    {"label": rides_month_label_short(row.year_month), "value": int(row.trip_count)}
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
                "kategorie_jazd_tableau": [
                    {"label": row.ride_category, "value": int(row.trip_count)}
                    for row in rides_categories.itertuples(index=False)
                ],
            },
            "vehicle_table": [
                {
                    "vehicle_id": row.vehicle_id,
                    "trip_count": int(row.trip_count),
                    "trip_share_pct": float(row.trip_share_pct),
                    "valid_trip_count": int(row.valid_trip_count),
                    "valid_share_pct": float(row.valid_share_pct),
                    "avg_trip_distance_km": round(float(row.avg_trip_distance_km), 2),
                    "dominant_category": row.dominant_category,
                }
                for row in trips_per_vehicle.itertuples(index=False)
            ],
            "route_table": [
                {
                    "route_summary_label": row.route_summary_label,
                    "tableau_route_label": row.trasa_tableau,
                    "record_count": int(row.record_count),
                    "avg_distance_km": round(float(row.avg_distance_km), 2),
                }
                for row in top_routes.itertuples(index=False)
            ],
            "raw_records": [
                {
                    "year_month": row.year_month,
                    "weekday_num": int(row.weekday_num),
                    "weekday_sk": row.weekday_sk,
                    "vehicle_id": row.vehicle_id,
                    "ew_start_raw": json_number_or_none(row.ew_start_raw),
                    "el_start_raw": json_number_or_none(row.el_start_raw),
                    "ride_category_tableau": row.ride_category_tableau,
                    "route_summary_label": row.route_summary_label,
                }
                for row in jazdy.itertuples(index=False)
            ],
            "comment": (
                f"Počet jázd v HTML je zrovnaný na COUNT([SPZ]) = {int(len(jazdy))}. "
                f"Najvyťaženejšie vozidlo podľa počtu jázd je {most_used_vehicle.vehicle_id} ({int(most_used_vehicle.trip_count)}), "
                f"najmenej jázd má {least_used_vehicle.vehicle_id} ({int(least_used_vehicle.trip_count)}). "
                f"Najsilnejší deň je {most_active_weekday.weekday_sk}. "
                f"Pri zapnutom filtri validných jázd ostáva {int(tableau_valid_jazdy.shape[0])} z {int(len(jazdy))} záznamov "
                f"({fmt_pct(jazdy['tableau_valid_trip'].mean() * 100)}). "
                f"Najčastejšia kategória je {top_ride_category.ride_category} ({int(top_ride_category.trip_count)}). "
                f"Najvyšší podiel validných jázd má {highest_valid_share_vehicle.vehicle_id} "
                f"({fmt_pct(float(highest_valid_share_vehicle.valid_share_pct))})."
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
            "jazdy": advanced_ride_analytics,
            "material": advanced_material_analytics,
        },
        "porovnanie_html_vs_tableau": {
            "message": (
                "RIDES sekcia v HTML je zosuladena s Tableau na urovni COUNT/COUNTD KPI, 6 kategorii jazd a logiky "
                "filtra Zobrazit iba validne jazdy. Plne mapove listy z Tableau HTML zamerne nenahradza interaktivnou mapou."
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
        sub_html = ""
        if card.get("sub"):
            sub_html = f'\n              <div class="kpi-sub">{escape(card["sub"])}</div>'
        items.append(
            f"""
            <div class="kpi-card" style="--accent:{card["color"]}">
              <div class="kpi-label">{escape(card["label"])}</div>
              <div class="kpi-value">{escape(card["value"])}</div>
              {sub_html}
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


def render_analysis_list(items: list[str], class_name: str = "analysis-list") -> str:
    return f"<ul class=\"{class_name}\">" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def render_analysis_summary_cards(cards: list[dict]) -> str:
    rendered = []
    for card in cards:
        value = card["value"]
        value_format = card.get("format", "int")
        if value_format == "pct1":
            value_text = fmt_pct(float(value), 1)
        elif value_format == "compact1":
            value_text = fmt_compact(float(value), 1)
        elif isinstance(value, float) and not float(value).is_integer():
            value_text = fmt_decimal(float(value), 1)
        else:
            value_text = fmt_int(int(round(float(value))))

        rendered.append(
            f"""
            <div class="analysis-summary-card">
              <div class="analysis-summary-label">{escape(card["label"])}</div>
              <div class="analysis-summary-value">{value_text}</div>
              <div class="analysis-summary-sub">{escape(card["sub"])}</div>
            </div>
            """
        )
    return "".join(rendered)


def build_html(dashboard: dict) -> str:
    understanding = dashboard["pochopenie_dat"]
    jazdy = dashboard["jazdy"]
    material = dashboard["material"]
    advanced = dashboard["pokrocilejsia_analytika"]
    meta = dashboard["meta"]

    header_cards = render_header_cards(meta["dataset_cards"])

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

    jazdy_section = f"""
    <section id="tab-jazdy" class="section">
      <div class="ride-section-head">
        <div class="ride-header-row">
          <div class="section-title">Jazdy vozidiel</div>
        </div>
        <div class="ride-toolbar">
          <div class="ride-toggle" role="group" aria-label="Ride mode toggle">
            <button type="button" class="ride-toggle-btn active" data-ride-mode="valid" aria-pressed="true">Valid rides only</button>
            <button type="button" class="ride-toggle-btn" data-ride-mode="all" aria-pressed="false">All rides</button>
          </div>
        </div>
        <p id="rideSummaryNote" class="ride-summary-note"></p>
      </div>
      <div id="ridesSectionContent"></div>
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

    ride_summary_cards = render_analysis_summary_cards(advanced["jazdy"]["summary_cards"])
    ride_method_list = render_analysis_list(advanced["jazdy"]["method_points"])
    ride_recommendation_list = render_analysis_list(
        advanced["jazdy"]["recommendations"], "analysis-list analysis-list-compact"
    )
    ride_review_rows = [
        [
            item["vehicle_id"],
            fmt_int(item["trip_count"]),
            fmt_int(item["inefficient_trip_count"]),
            fmt_pct(item["inefficient_share_pct"], 1),
            fmt_pct(item["near_zero_share_pct"], 1),
            fmt_pct(item["short_share_pct"], 1),
            fmt_decimal(item["review_score"], 1),
            item["priority_band"],
        ]
        for item in advanced["jazdy"]["table"]
    ]

    material_summary_cards = render_analysis_summary_cards(advanced["material"]["summary_cards"])
    material_method_list = render_analysis_list(advanced["material"]["method_points"])
    material_recommendation_list = render_analysis_list(
        advanced["material"]["recommendations"], "analysis-list analysis-list-compact"
    )
    material_segment_rows = [
        [
            item["segment"],
            fmt_int(item["prefix_count"]),
            fmt_pct(item["movement_share_pct"], 1),
            fmt_pct(item["quantity_share_pct"], 1),
        ]
        for item in advanced["material"]["segment_table"]
    ]
    material_priority_rows = [
        [
            item["material_prefix"],
            item["segment"],
            fmt_pct(item["movement_share_pct"], 1),
            fmt_pct(item["quantity_share_pct"], 1),
            fmt_int(item["active_months"]),
            fmt_pct(item["peak_month_share_pct"], 1),
            item["reason"],
        ]
        for item in advanced["material"]["priority_table"]
    ]

    advanced_section = f"""
    <section id="tab-pokrocila" class="section">
      <div class="section-title">Pokročilejšia analytika</div>
      <p class="section-copy">
        Táto časť už neukazuje len opisné KPI. Pre každý dataset formuluje konkrétnu analytickú úlohu, stručne vysvetlí
        metódu, zobrazí dátový výsledok a pridá interpretáciu, ktorú sa dá obhájiť pri prezentácii.
      </p>

      <div class="analysis-report">
        <div class="analysis-head">
          <div class="analysis-kicker">Dataset 1 | Jazdy vozidiel</div>
          <div class="card-title">Pokročilá úloha: identifikácia vozidiel s podozrivou neefektivitou</div>
          <div class="analysis-label">Analytická otázka</div>
          <p class="analysis-question">{escape(advanced["jazdy"]["question"])}</p>
        </div>

        <div class="analysis-grid">
          <div class="analysis-block">
            <div class="analysis-block-title">Metóda</div>
            <div class="analysis-method-title">{escape(advanced["jazdy"]["method_title"])}</div>
            {ride_method_list}
          </div>
          <div class="analysis-block">
            <div class="analysis-block-title">Výsledok v skratke</div>
            <p class="analysis-body">{escape(advanced["jazdy"]["result_text"])}</p>
            <div class="analysis-summary-grid">{ride_summary_cards}</div>
          </div>
        </div>

        <div class="analysis-grid">
          <div class="card canvas-card">
            <div class="card-title">Rebríček vozidiel podľa prioritizačného skóre</div>
            <p class="table-intro">Vyššie skóre znamená väčšiu koncentráciu označených, near-zero a krátkych jázd.</p>
            <canvas id="chartRideReviewScore" height="250"></canvas>
          </div>
          {render_table(
              "Vozidlá na prioritný review",
              [
                  "Vozidlo",
                  "Jazdy",
                  "Označené",
                  "Podiel označených",
                  "Near-zero",
                  "Krátke jazdy",
                  "Prioritizačné skóre",
                  "Priorita",
              ],
              ride_review_rows,
              intro="Tabuľka spája viac signálov do jednej transparentnej priority pre manuálnu kontrolu vozidiel.",
          )}
        </div>

        <div class="analysis-grid">
          <div class="analysis-callout">
            <div class="analysis-block-title">Interpretácia</div>
            <p class="analysis-body">{escape(advanced["jazdy"]["interpretation"])}</p>
          </div>
          <div class="analysis-callout analysis-callout-warm">
            <div class="analysis-block-title">Odporúčanie</div>
            {ride_recommendation_list}
          </div>
        </div>
      </div>

      <div class="analysis-report">
        <div class="analysis-head">
          <div class="analysis-kicker">Dataset 2 | Pohyby materiálu</div>
          <div class="card-title">Pokročilá úloha: segmentácia prefixov podľa prevádzkového rizika</div>
          <div class="analysis-label">Analytická otázka</div>
          <p class="analysis-question">{escape(advanced["material"]["question"])}</p>
        </div>

        <div class="analysis-grid">
          <div class="analysis-block">
            <div class="analysis-block-title">Metóda</div>
            <div class="analysis-method-title">{escape(advanced["material"]["method_title"])}</div>
            {material_method_list}
          </div>
          <div class="analysis-block">
            <div class="analysis-block-title">Výsledok v skratke</div>
            <p class="analysis-body">{escape(advanced["material"]["result_text"])}</p>
            <div class="analysis-summary-grid">{material_summary_cards}</div>
          </div>
        </div>

        <div class="analysis-grid">
          <div class="card canvas-card">
            <div class="card-title">Podiel objemu podľa segmentu</div>
            <p class="table-intro">Graf ukazuje, v ktorých segmentoch sa koncentruje celkové množstvo materiálu.</p>
            <canvas id="chartMaterialSegmentsAdvanced" height="250"></canvas>
          </div>
          {render_table(
              "Prehľad segmentov prefixov",
              [
                  "Segment",
                  "Prefixy",
                  "Podiel pohybov",
                  "Podiel množstva",
              ],
              material_segment_rows,
              intro="Segmenty oddeľujú stabilné skupiny od prefixov s vysokým dopadom alebo neštandardnou koncentráciou aktivity.",
          )}
        </div>

        {render_table(
            "Prefixy na prioritný monitoring",
            [
                "Prefix",
                "Segment",
                "Podiel pohybov",
                "Podiel množstva",
                "Aktívne mesiace",
                "Peak mesiac",
                "Dôvod",
            ],
            material_priority_rows,
            intro="Tabuľka zvýrazňuje prefixy, ktoré majú najväčší objemový dopad alebo neštandardne koncentrované správanie.",
        )}

        <div class="analysis-grid">
          <div class="analysis-callout">
            <div class="analysis-block-title">Interpretácia</div>
            <p class="analysis-body">{escape(advanced["material"]["interpretation"])}</p>
          </div>
          <div class="analysis-callout analysis-callout-warm">
            <div class="analysis-block-title">Odporúčanie</div>
            {material_recommendation_list}
          </div>
        </div>
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

    .ride-section-head {
      margin-bottom: 18px;
    }

    .ride-header-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }

    .ride-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }

    .ride-toggle {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 4px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(13, 24, 43, 0.8);
      box-shadow: var(--shadow);
    }

    .ride-toggle-btn {
      appearance: none;
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: var(--text-dim);
      cursor: pointer;
      font-family: var(--font-head);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.01em;
      padding: 10px 16px;
      transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
    }

    .ride-toggle-btn:hover {
      color: var(--text);
      transform: translateY(-1px);
    }

    .ride-toggle-btn.active {
      background: linear-gradient(135deg, rgba(0, 212, 255, 0.96), rgba(106, 239, 255, 0.88));
      color: #04101c;
      box-shadow: 0 10px 26px rgba(0, 212, 255, 0.22);
    }

    .ride-summary-note {
      margin: 0;
      color: var(--text-soft);
      max-width: 1080px;
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
      grid-template-columns: repeat(auto-fit, minmax(172px, 1fr));
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

    .analysis-report {
      position: relative;
      overflow: hidden;
      margin-bottom: 24px;
      padding: 24px;
      border: 1px solid rgba(0, 212, 255, 0.16);
      border-radius: var(--radius-lg);
      background:
        linear-gradient(180deg, rgba(12, 23, 40, 0.98), rgba(10, 18, 33, 0.96)),
        radial-gradient(circle at top right, rgba(0, 212, 255, 0.08), transparent 30%);
      box-shadow: var(--shadow);
    }

    .analysis-report::before {
      content: "";
      position: absolute;
      inset: 0 0 auto;
      height: 3px;
      background: linear-gradient(90deg, var(--accent1), rgba(255, 122, 69, 0.6), transparent 82%);
    }

    .analysis-head {
      margin-bottom: 18px;
    }

    .analysis-kicker,
    .analysis-label,
    .analysis-block-title,
    .analysis-summary-label {
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 1.2px;
      text-transform: uppercase;
    }

    .analysis-kicker {
      color: var(--accent1);
      margin-bottom: 8px;
    }

    .analysis-label,
    .analysis-block-title,
    .analysis-summary-label {
      color: var(--text-dim);
    }

    .analysis-question {
      margin: 8px 0 0;
      max-width: 980px;
      font-family: var(--font-head);
      font-size: clamp(22px, 2.3vw, 30px);
      line-height: 1.22;
      letter-spacing: -0.02em;
    }

    .analysis-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      margin-bottom: 18px;
    }

    .analysis-block,
    .analysis-callout {
      padding: 20px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(88, 118, 165, 0.2);
      background: linear-gradient(180deg, rgba(17, 30, 52, 0.96), rgba(13, 24, 43, 0.94));
    }

    .analysis-method-title {
      margin: 6px 0 0;
      font-family: var(--font-head);
      font-size: 18px;
      line-height: 1.2;
    }

    .analysis-body {
      margin: 8px 0 0;
      color: var(--text-soft);
      font-size: 14px;
      max-width: none;
    }

    .analysis-list {
      margin: 12px 0 0;
      padding-left: 18px;
      color: var(--text-soft);
      font-size: 13px;
    }

    .analysis-list-compact {
      margin-top: 8px;
    }

    .analysis-summary-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin-top: 18px;
    }

    .analysis-summary-card {
      padding: 16px;
      border-radius: var(--radius-md);
      border: 1px solid rgba(88, 118, 165, 0.18);
      background: linear-gradient(180deg, rgba(20, 34, 56, 0.98), rgba(14, 25, 43, 0.96));
    }

    .analysis-summary-value {
      margin-top: 8px;
      font-family: var(--font-head);
      font-size: 28px;
      line-height: 1;
    }

    .analysis-summary-sub {
      margin-top: 6px;
      color: var(--text-soft);
      font-size: 12px;
    }

    .analysis-callout-warm {
      border-color: rgba(255, 122, 69, 0.26);
      background: linear-gradient(180deg, rgba(35, 25, 25, 0.96), rgba(24, 19, 24, 0.94));
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

    .donut-panel {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 250px;
      gap: 18px;
      align-items: center;
      min-height: 260px;
    }

    .donut-canvas-wrap {
      min-width: 0;
    }

    .donut-legend {
      display: grid;
      gap: 10px;
      align-content: center;
    }

    .donut-legend-item {
      appearance: none;
      width: 100%;
      display: grid;
      grid-template-columns: 10px minmax(0, 1fr);
      column-gap: 12px;
      row-gap: 3px;
      align-items: start;
      padding: 12px 14px;
      border: 1px solid rgba(88, 118, 165, 0.22);
      border-radius: 16px;
      background: linear-gradient(180deg, rgba(17, 30, 52, 0.92), rgba(12, 22, 38, 0.94));
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
      color: inherit;
      cursor: pointer;
      text-align: left;
      transition:
        border-color 0.18s ease,
        background 0.18s ease,
        transform 0.18s ease,
        box-shadow 0.18s ease,
        opacity 0.18s ease;
    }

    .donut-legend-item:hover {
      transform: translateY(-1px);
    }

    .donut-legend-item:focus-visible {
      outline: 0;
      border-color: rgba(0, 212, 255, 0.58);
      box-shadow:
        0 0 0 3px rgba(0, 212, 255, 0.14),
        0 14px 28px rgba(0, 0, 0, 0.2);
    }

    .donut-legend-item.active {
      border-color: rgba(0, 212, 255, 0.34);
      background: linear-gradient(180deg, rgba(21, 38, 66, 0.98), rgba(14, 26, 46, 0.96));
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.03),
        0 16px 30px rgba(0, 0, 0, 0.18);
    }

    .donut-legend-item.dim {
      border-color: rgba(88, 118, 165, 0.1);
      background: linear-gradient(180deg, rgba(11, 19, 33, 0.82), rgba(9, 16, 29, 0.86));
    }

    .donut-legend-swatch {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      margin-top: 4px;
      box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.03);
    }

    .donut-legend-label {
      color: var(--text);
      font-family: var(--font-body);
      font-size: 13px;
      font-weight: 700;
      line-height: 1.25;
    }

    .donut-legend-meta {
      color: var(--text-soft);
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .donut-legend-item.dim .donut-legend-label,
    .donut-legend-item.dim .donut-legend-meta {
      color: #7688a0;
    }

    .donut-legend-item.dim .donut-legend-swatch {
      opacity: 0.42;
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
      .insight-grid,
      .analysis-grid {
        grid-template-columns: 1fr;
      }

      .meta-strip {
        grid-template-columns: 1fr;
      }

      .donut-panel {
        grid-template-columns: 1fr;
      }

      .donut-legend {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 760px) {
      .kpi-row,
      .signal-grid,
      .analysis-summary-grid {
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

      .donut-legend {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="page-shell">
      <h1>Analyticky <span>Dashboard</span></h1>

      <div class="meta-strip">__HEADER_DATASET_CARDS__</div>
    </div>
  </header>

  <div class="tabs-wrap">
    <div class="page-shell">
      <div class="tabs" role="tablist" aria-label="Dashboard sections">
        <button class="tab active" data-tab="pochopenie" aria-selected="true">Pochopenie dat</button>
        <button class="tab" data-tab="jazdy" aria-selected="false">Jazdy vozidiel</button>
        <button class="tab" data-tab="material" aria-selected="false">Pohyby materialu</button>
        <button class="tab" data-tab="pokrocila" aria-selected="false">Pokročilejšia analytika</button>
      </div>
    </div>
  </div>

  <main>
    __UNDERSTANDING_SECTION__
    __JAZDY_SECTION__
    __MATERIAL_SECTION__
    __ADVANCED_SECTION__
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
    const rideSummaryNote = document.getElementById("rideSummaryNote");
    const ridesSectionContent = document.getElementById("ridesSectionContent");
    const ridesMonthOrder = [
      "Jan", "Feb", "Mar", "Apr", "Maj", "Jun",
      "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"
    ];
    const rideWeekdayOrder = ["Po", "Ut", "St", "Stv", "Pi", "So", "Ne"];
    const rideCategoryOrder = [
      "Žiadna jazda (0m)",
      "Parkovanie (<100m)",
      "Krátka (100m-1km)",
      "Mestská (1-5km)",
      "Regionálna (5-50km)",
      "Diaľková (>50km)"
    ];

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

    function formatPercent(value, digits = 1) {
      return formatNumber(value, digits) + " %";
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function monthFromYearMonth(value) {
      const parts = String(value || "").split("-");
      return Number(parts[1] || 0);
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

    function renderInteractiveDonutLegend(state) {
      if (!state.legendContainer) {
        return;
      }

      state.legendContainer.innerHTML = state.items.map((item, index) => {
        const value = Number(item.value);
        const pct = Math.round((value / state.total) * 100);
        const color = state.colors[index % state.colors.length];
        const legendValue = `${state.formatter(value)} | ${pct}%`;

        return `
          <button
            type="button"
            class="donut-legend-item"
            aria-label="${escapeHtml(item.label)}: ${escapeHtml(legendValue)}"
            data-donut-index="${index}"
          >
            <span class="donut-legend-swatch" style="background:${color}"></span>
            <span class="donut-legend-label">${escapeHtml(item.label)}</span>
            <span class="donut-legend-meta">${escapeHtml(legendValue)}</span>
          </button>
        `;
      }).join("");

      state.legendItems = Array.from(state.legendContainer.querySelectorAll(".donut-legend-item"));

      state.legendItems.forEach((button, index) => {
        button.addEventListener("mouseenter", () => {
          setInteractiveDonutSource(state, "legend", index);
        });

        button.addEventListener("mouseleave", () => {
          setInteractiveDonutSource(state, "legend", null);
        });

        button.addEventListener("focus", () => {
          setInteractiveDonutSource(state, "legend", index);
        });

        button.addEventListener("blur", () => {
          setInteractiveDonutSource(state, "legend", null);
        });
      });
    }

    function updateInteractiveDonutLegend(state) {
      if (!state.legendItems) {
        return;
      }

      state.legendItems.forEach((button, index) => {
        const isActive = state.activeIndex === index;
        const shouldDim = state.activeIndex !== null && !isActive;
        button.classList.toggle("active", isActive);
        button.classList.toggle("dim", shouldDim);
      });
    }

    function getInteractiveDonutActiveIndex(state) {
      if (state.activeSources.legend !== null) {
        return state.activeSources.legend;
      }
      return state.activeSources.canvas;
    }

    function renderInteractiveDonut(state) {
      const { ctx, width, height } = state;
      ctx.clearRect(0, 0, width, height);
      ctx.lineJoin = "round";

      let startAngle = state.startAngle;
      state.geometry = [];

      state.items.forEach((item, index) => {
        const value = Number(item.value);
        const slice = (value / state.total) * Math.PI * 2;
        const endAngle = startAngle + slice;
        const midAngle = startAngle + slice / 2;
        const progress = state.sliceProgress[index] || 0;
        const explodeOffset = 10 * progress;
        const translateX = Math.cos(midAngle) * explodeOffset;
        const translateY = Math.sin(midAngle) * explodeOffset - (1.5 * progress);
        const isActive = state.activeIndex === index;
        const hasActive = state.activeIndex !== null;

        ctx.save();
        ctx.translate(translateX, translateY);
        ctx.globalAlpha = hasActive && !isActive ? 0.28 : 1;
        ctx.beginPath();
        ctx.arc(state.centerX, state.centerY, state.radius, startAngle, endAngle);
        ctx.arc(state.centerX, state.centerY, state.innerRadius, endAngle, startAngle, true);
        ctx.closePath();
        ctx.fillStyle = state.colors[index % state.colors.length];
        ctx.fill();
        ctx.lineWidth = isActive ? 2 : 1;
        ctx.strokeStyle = isActive ? "rgba(235, 241, 251, 0.28)" : "rgba(13, 24, 43, 0.78)";
        ctx.stroke();
        ctx.restore();

        state.geometry.push({
          startAngle,
          endAngle,
          label: item.label,
          tooltipValue: `${state.formatter(value)} | ${Math.round((value / state.total) * 100)}%`,
        });

        startAngle = endAngle;
      });

      ctx.beginPath();
      ctx.arc(state.centerX, state.centerY, state.innerRadius - 1, 0, Math.PI * 2);
      ctx.fillStyle = palette.hole;
      ctx.fill();

      ctx.fillStyle = palette.textSoft;
      ctx.font = "10px DM Mono";
      ctx.textAlign = "center";
      ctx.fillText("TOTAL", state.centerX, state.centerY - 4);
      ctx.fillStyle = palette.text;
      ctx.font = "bold 18px Syne";
      ctx.fillText(state.formatter(state.total), state.centerX, state.centerY + 20);
    }

    function animateInteractiveDonut(state) {
      state.rafId = 0;
      let needsNextFrame = false;

      state.sliceProgress = state.sliceProgress.map((progress, index) => {
        const target = state.activeIndex === index ? 1 : 0;
        const next = progress + ((target - progress) * 0.18);
        if (Math.abs(target - next) > 0.01) {
          needsNextFrame = true;
        }
        return next;
      });

      renderInteractiveDonut(state);

      if (needsNextFrame) {
        state.rafId = window.requestAnimationFrame(() => animateInteractiveDonut(state));
      }
    }

    function ensureInteractiveDonutAnimation(state) {
      if (state.rafId) {
        return;
      }

      state.rafId = window.requestAnimationFrame(() => animateInteractiveDonut(state));
    }

    function setInteractiveDonutSource(state, source, index) {
      if (!state) {
        return;
      }

      state.activeSources[source] = index;
      const nextActiveIndex = getInteractiveDonutActiveIndex(state);
      if (state.activeIndex === nextActiveIndex) {
        updateInteractiveDonutLegend(state);
        return;
      }

      state.activeIndex = nextActiveIndex;
      updateInteractiveDonutLegend(state);
      ensureInteractiveDonutAnimation(state);
    }

    function getInteractiveDonutHitIndex(state, x, y) {
      const dx = x - state.centerX;
      const dy = y - state.centerY;
      const distance = Math.sqrt((dx * dx) + (dy * dy));
      if (distance < state.innerRadius - 8 || distance > state.radius + 12) {
        return null;
      }

      let angle = Math.atan2(dy, dx);
      while (angle < state.startAngle) {
        angle += Math.PI * 2;
      }

      const hit = (state.geometry || []).find((segment) => angle >= segment.startAngle && angle <= segment.endAngle);
      return hit ? state.geometry.indexOf(hit) : null;
    }

    function drawInteractiveDonutChart(id, items, colors, options = {}) {
      const setup = prepCanvas(id);
      if (!setup || !items.length) return;

      const { canvas, ctx, width, height } = setup;
      const legendContainer = document.getElementById(options.legendId);
      const formatter = options.formatter || ((value) => formatNumber(value, 0));
      const total = items.reduce((sum, item) => sum + Number(item.value), 0) || 1;
      const radius = Math.min(width * 0.28, height * 0.34);
      const state = {
        canvas,
        ctx,
        width,
        height,
        items,
        colors,
        legendContainer,
        formatter,
        total,
        centerX: width / 2,
        centerY: height / 2,
        radius,
        innerRadius: radius * 0.6,
        startAngle: -Math.PI / 2,
        activeIndex: null,
        activeSources: {
          canvas: null,
          legend: null,
        },
        sliceProgress: Array(items.length).fill(0),
        legendItems: [],
        geometry: [],
        rafId: 0,
      };

      if (canvas.__interactiveDonutState?.rafId) {
        window.cancelAnimationFrame(canvas.__interactiveDonutState.rafId);
      }

      canvas.__interactiveDonutState = state;
      canvas.setAttribute("role", "img");
      canvas.setAttribute(
        "aria-label",
        "Kategórie jázd podľa Tableau. Fokusuj legendu pre zvýraznenie zodpovedajúceho segmentu."
      );

      renderInteractiveDonutLegend(state);
      updateInteractiveDonutLegend(state);
      renderInteractiveDonut(state);

      if (canvas.dataset.interactiveDonutBound === "true") {
        return;
      }

      canvas.dataset.interactiveDonutBound = "true";
      canvas.addEventListener("mousemove", (event) => {
        const currentState = canvas.__interactiveDonutState;
        if (!currentState) {
          return;
        }

        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        const hitIndex = getInteractiveDonutHitIndex(currentState, x, y);

        canvas.style.cursor = hitIndex === null ? "default" : "pointer";
        setInteractiveDonutSource(currentState, "canvas", hitIndex);

        if (hitIndex === null) {
          hideChartTooltip();
          return;
        }

        const segment = currentState.geometry[hitIndex];
        showChartTooltip(event, {
          label: segment.label,
          tooltipValue: segment.tooltipValue,
        });
      });

      canvas.addEventListener("mouseleave", () => {
        const currentState = canvas.__interactiveDonutState;
        canvas.style.cursor = "default";
        hideChartTooltip();
        setInteractiveDonutSource(currentState, "canvas", null);
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

    // The HTML rides toggle mirrors the Tableau valid/all rides parameter.
    // Every mode change rebuilds KPIs, charts, tables and summary text from one filtered rides array.
    function isValidRide(record) {
      // EW_START and EL_START are stored in this HTML dataset as integer-like coordinates with six implied decimals,
      // so we scale by 1_000_000 here before applying the valid-ride bounds.
      const latStart = Number(record.ew_start_raw) / 1000000;
      const lonStart = Number(record.el_start_raw) / 1000000;
      return Number.isFinite(latStart)
        && Number.isFinite(lonStart)
        && lonStart >= 16.5
        && lonStart <= 23.6
        && latStart >= 47.7
        && latStart <= 49.7;
    }

    function enrichRideRecord(record) {
      const latStart = Number(record.ew_start_raw) / 1000000;
      const lonStart = Number(record.el_start_raw) / 1000000;
      return {
        ...record,
        latStart,
        lonStart,
        validRide: isValidRide(record),
        zeroDistance: record.ride_category_tableau === "Žiadna jazda (0m)"
      };
    }

    const rideState = {
      showValidOnly: true,
      allRides: (dashboard.jazdy.raw_records || []).map((record) => enrichRideRecord(record)),
      currentView: null
    };

    function incrementCounter(map, key) {
      map.set(key, (map.get(key) || 0) + 1);
    }

    function getOrderedCountItems(order, records, getLabel) {
      const counts = new Map(order.map((label) => [label, 0]));
      records.forEach((record) => {
        const label = getLabel(record);
        if (counts.has(label)) {
          counts.set(label, counts.get(label) + 1);
        }
      });
      return order.map((label) => ({
        label,
        value: counts.get(label) || 0
      }));
    }

    function pickTopItem(items) {
      return [...items].sort((a, b) => {
        if (Number(b.value) !== Number(a.value)) {
          return Number(b.value) - Number(a.value);
        }
        return String(a.label).localeCompare(String(b.label), "sk");
      })[0] || null;
    }

    function getFilteredRides(showValidOnly) {
      return showValidOnly
        ? rideState.allRides.filter((ride) => ride.validRide)
        : [...rideState.allRides];
    }

    function computeVehicleBreakdown(filteredRides) {
      const vehicleMap = new Map();

      filteredRides.forEach((ride) => {
        if (!vehicleMap.has(ride.vehicle_id)) {
          vehicleMap.set(ride.vehicle_id, {
            vehicle_id: ride.vehicle_id,
            tripCount: 0,
            validTripCount: 0,
            categoryCounts: new Map()
          });
        }

        const vehicle = vehicleMap.get(ride.vehicle_id);
        vehicle.tripCount += 1;
        if (ride.validRide) {
          vehicle.validTripCount += 1;
        }
        incrementCounter(vehicle.categoryCounts, ride.ride_category_tableau);
      });

      const totalRideCount = filteredRides.length || 1;

      return [...vehicleMap.values()]
        .map((vehicle) => {
          const dominantCategory = rideCategoryOrder
            .map((label, index) => ({
              label,
              count: vehicle.categoryCounts.get(label) || 0,
              index
            }))
            .sort((a, b) => {
              if (b.count !== a.count) {
                return b.count - a.count;
              }
              return a.index - b.index;
            })[0]?.label || "Bez kategórie";

          return {
            vehicle_id: vehicle.vehicle_id,
            tripCount: vehicle.tripCount,
            tripSharePct: (vehicle.tripCount / totalRideCount) * 100,
            validTripCount: vehicle.validTripCount,
            validSharePct: vehicle.tripCount ? (vehicle.validTripCount / vehicle.tripCount) * 100 : 0,
            dominantCategory
          };
        })
        .sort((a, b) => {
          if (b.tripCount !== a.tripCount) {
            return b.tripCount - a.tripCount;
          }
          return a.vehicle_id.localeCompare(b.vehicle_id, "sk");
        });
    }

    function computeRideMetrics(filteredRides, vehicleBreakdown, showValidOnly) {
      const totalRideCount = filteredRides.length;
      const vehicleCount = vehicleBreakdown.length;
      const validRideCount = filteredRides.filter((ride) => ride.validRide).length;
      const invalidRideCount = totalRideCount - validRideCount;
      const zeroDistanceCount = filteredRides.filter((ride) => ride.zeroDistance).length;
      const weekdayItems = getOrderedCountItems(rideWeekdayOrder, filteredRides, (ride) => ride.weekday_sk);
      const categoryItems = getOrderedCountItems(rideCategoryOrder, filteredRides, (ride) => ride.ride_category_tableau);
      const routeReadyCount = filteredRides.filter((ride) => ride.route_summary_label).length;

      return {
        totalRideCount,
        vehicleCount,
        averageRidesPerVehicle: vehicleCount ? Math.round(totalRideCount / vehicleCount) : 0,
        validRideCount,
        invalidRideCount,
        zeroDistanceCount,
        topWeekday: pickTopItem(weekdayItems),
        topCategory: pickTopItem(categoryItems),
        topVehicle: vehicleBreakdown[0] || null,
        leastUsedVehicle: vehicleBreakdown[vehicleBreakdown.length - 1] || null,
        routeReadyCount,
        showValidOnly,
      };
    }

    function computeRideCharts(filteredRides, vehicleBreakdown) {
      const monthlyItems = ridesMonthOrder.map((label) => ({ label, value: 0 }));
      const monthlyMap = new Map(ridesMonthOrder.map((label, index) => [label, index]));

      filteredRides.forEach((ride) => {
        const monthIndex = monthFromYearMonth(ride.year_month) - 1;
        const label = ridesMonthOrder[monthIndex];
        if (monthlyMap.has(label)) {
          monthlyItems[monthlyMap.get(label)].value += 1;
        }
      });

      return {
        monthly: monthlyItems,
        weekday: getOrderedCountItems(rideWeekdayOrder, filteredRides, (ride) => ride.weekday_sk),
        categories: getOrderedCountItems(rideCategoryOrder, filteredRides, (ride) => ride.ride_category_tableau),
        topVehicles: vehicleBreakdown.slice(0, 8).map((item) => ({
          label: item.vehicle_id,
          value: item.tripCount
        }))
      };
    }

    function computeRideRoutes(filteredRides) {
      const routeMap = new Map();

      filteredRides.forEach((ride) => {
        if (!ride.route_summary_label) {
          return;
        }
        incrementCounter(routeMap, ride.route_summary_label);
      });

      return [...routeMap.entries()]
        .map(([routeSummaryLabel, recordCount]) => ({
          routeSummaryLabel,
          recordCount
        }))
        .sort((a, b) => {
          if (b.recordCount !== a.recordCount) {
            return b.recordCount - a.recordCount;
          }
          return a.routeSummaryLabel.localeCompare(b.routeSummaryLabel, "sk");
        })
        .slice(0, 8);
    }

    function buildRideView(showValidOnly) {
      const filteredRides = getFilteredRides(showValidOnly);
      const vehicleBreakdown = computeVehicleBreakdown(filteredRides);
      const metrics = computeRideMetrics(filteredRides, vehicleBreakdown, showValidOnly);
      const charts = computeRideCharts(filteredRides, vehicleBreakdown);
      const routes = computeRideRoutes(filteredRides);

      return {
        showValidOnly,
        filteredRides,
        metrics,
        charts,
        vehicles: vehicleBreakdown,
        routes,
        summary: buildRideSummary(metrics)
      };
    }

    function buildRideSummary(metrics) {
      if (!metrics.totalRideCount) {
        return "V zvolenom móde nie sú žiadne jazdy.";
      }

      const strongestDay = metrics.topWeekday ? metrics.topWeekday.label : "n/a";
      const topCategory = metrics.topCategory ? metrics.topCategory.label : "n/a";
      const topVehicle = metrics.topVehicle
        ? `${metrics.topVehicle.vehicle_id} (${formatNumber(metrics.topVehicle.tripCount, 0)})`
        : "n/a";
      const scopeIntro = metrics.showValidOnly
        ? "Zobrazené sú iba jazdy vo validnom rozsahu."
        : "Zobrazené sú všetky jazdy vrátane záznamov mimo validného rozsahu.";

      return `${scopeIntro} ${formatNumber(metrics.totalRideCount, 0)} jázd naprieč `
        + `${formatNumber(metrics.vehicleCount, 0)} vozidlami. Najsilnejší deň je ${strongestDay}, `
        + `najčastejšia kategória ${topCategory} a najvyťaženejšie vozidlo ${topVehicle}.`;
    }

    function renderRideKPIs(metrics) {
      const cards = [
        { label: "Počet jázd", value: formatNumber(metrics.totalRideCount, 0), color: palette.accent1 },
        { label: "Počet vozidiel", value: formatNumber(metrics.vehicleCount, 0), color: palette.accent2 },
        { label: "Priem. jazdy / vozidlo", value: formatNumber(metrics.averageRidesPerVehicle, 0), color: palette.accent3 },
        { label: "Validné jazdy", value: formatNumber(metrics.validRideCount, 0), color: palette.accent4 },
        { label: "Žiadna jazda (0m)", value: formatNumber(metrics.zeroDistanceCount, 0), color: palette.accent2 }
      ];

      if (!metrics.showValidOnly) {
        cards.splice(4, 0, {
          label: "Mimo validného rozsahu",
          value: formatNumber(metrics.invalidRideCount, 0),
          color: palette.accent1,
        });
      }

      return `
        <div class="kpi-row">
          ${cards.map((card) => `
            <div class="kpi-card" style="--accent:${card.color}">
              <div class="kpi-label">${escapeHtml(card.label)}</div>
              <div class="kpi-value">${escapeHtml(card.value)}</div>
            </div>
          `).join("")}
        </div>
      `;
    }

    function renderRideTableCard(title, headers, rows, intro = "") {
      const headerHtml = headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("");
      const rowHtml = rows.length
        ? rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")
        : `<tr><td colspan="${headers.length}">Bez dostupných záznamov</td></tr>`;

      return `
        <div class="card table-card">
          <div class="card-title">${escapeHtml(title)}</div>
          ${intro ? `<p class="table-intro">${escapeHtml(intro)}</p>` : ""}
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr>${headerHtml}</tr></thead>
              <tbody>${rowHtml}</tbody>
            </table>
          </div>
        </div>
      `;
    }

    function renderRideTables(view) {
      const vehicleRows = view.vehicles.slice(0, 10).map((item) => ([
        item.vehicle_id,
        formatNumber(item.tripCount, 0),
        formatPercent(item.tripSharePct, 1),
        formatNumber(item.validTripCount, 0),
        formatPercent(item.validSharePct, 1),
        item.dominantCategory
      ]));

      const routeRows = view.routes.map((item) => ([
        item.routeSummaryLabel,
        formatNumber(item.recordCount, 0)
      ]));

      return `
        ${renderRideTableCard(
          "Vyťaženosť vozidiel",
          ["Vozidlo", "Počet jázd", "Podiel zo všetkých", "Validné jazdy", "Podiel validných", "Dominantná kategória"],
          vehicleRows,
          "Vyťaženosť je vždy počítaná z aktuálne zvoleného módu, nie z pevne predpripravených agregácií."
        )}

        <div class="grid-2">
          ${renderRideTableCard(
            "Top trasy podľa počtu záznamov",
            ["Trasa podľa štart/cieľ súradníc", "Záznamy"],
            routeRows,
            "Tabuľka zoraďuje coordinate-based štart/cieľ páry len z práve zobrazeného datasetu jázd."
          )}

          <div class="card">
            <div class="card-title">Priestorové pohľady z Tableau</div>
            <p class="card-intro">
              Tableau má mapové listy, ale HTML ostáva pri textovej súradnicovej sumarizácii, aby z priamej vzdialenosti
              netvrdilo skutočnú trasu po cestách.
            </p>
            <ul class="validation-list">
              <li>${view.showValidOnly ? "Zobrazené sú iba validné jazdy podľa Tableau bounds." : "Zobrazené sú všetky jazdy vrátane záznamov mimo validného rozsahu."}</li>
              <li>Práve zobrazený dataset obsahuje ${formatNumber(view.metrics.totalRideCount, 0)} jázd.</li>
              <li>${formatNumber(view.metrics.routeReadyCount, 0)} jázd má normalizovaný štart/cieľ pár použiteľný pre route summary.</li>
              <li>Valid ride v HTML používa štartové bounds 16,5-23,6 / 47,7-49,7 po delení EW_START a EL_START hodnotou 1 000 000.</li>
            </ul>
          </div>
        </div>
      `;
    }

    function renderRideSection(view) {
      if (!ridesSectionContent) {
        return;
      }

      if (rideSummaryNote) {
        rideSummaryNote.textContent = view.summary;
      }

      ridesSectionContent.innerHTML = `
        ${renderRideKPIs(view.metrics)}

        <div class="grid-2">
          <div class="card canvas-card">
            <div class="card-title">Vývoj jázd v čase</div>
            <canvas id="chartMonthlyTrips" height="220"></canvas>
          </div>
          <div class="card canvas-card">
            <div class="card-title">Jazdy podľa dňa</div>
            <canvas id="chartWeekdayTrips" height="220"></canvas>
          </div>
        </div>

        <div class="grid-13">
          <div class="card canvas-card">
            <div class="card-title">Kategórie jázd podľa Tableau</div>
            <div class="donut-panel">
              <div class="donut-canvas-wrap">
                <canvas id="chartTripDistance" height="260"></canvas>
              </div>
              <div id="chartTripDistanceLegend" class="donut-legend" aria-label="Legenda kategórií jázd podľa Tableau"></div>
            </div>
          </div>
          <div class="card canvas-card">
            <div class="card-title">Vyťaženosť vozidiel podľa počtu jázd</div>
            <canvas id="chartTopVehicles" height="260"></canvas>
          </div>
        </div>

        ${renderRideTables(view)}

        <div class="insight">
          <strong>Rychla interpretacia:</strong>
          V tomto móde sa KPI, grafy, tabuľky aj route summary rátajú z toho istého filtrovaného datasetu jázd.
        </div>
      `;
    }

    function updateRideModeUI(showValidOnly) {
      const modeKey = showValidOnly ? "valid" : "all";

      document.querySelectorAll(".ride-toggle-btn").forEach((button) => {
        const isActive = button.dataset.rideMode === modeKey;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
    }

    function setRideMode(showValidOnly) {
      rideState.showValidOnly = showValidOnly;
      rideState.currentView = buildRideView(showValidOnly);
      hideChartTooltip();
      updateRideModeUI(showValidOnly);
      renderRideSection(rideState.currentView);

      // Replacing the rides DOM recreates the canvases, so the custom charts are redrawn once per mode change.
      if (activeTab === "jazdy") {
        requestAnimationFrame(() => drawTripsCharts(rideState.currentView));
      }
    }

    function drawTripsCharts(view = rideState.currentView) {
      if (!view) return;

      drawBarChart(
        "chartMonthlyTrips",
        view.charts.monthly,
        palette.accent1,
        (value) => formatNumber(value, 0),
        { tooltip: true }
      );
      drawBarChart(
        "chartWeekdayTrips",
        view.charts.weekday,
        palette.accent4,
        (value) => formatNumber(value, 0),
        { tooltip: true }
      );
      drawInteractiveDonutChart(
        "chartTripDistance",
        view.charts.categories,
        [palette.accent2, palette.accent1, palette.accent3, palette.accent4, "#9f7aea", "#ffb86c"],
        { legendId: "chartTripDistanceLegend" }
      );
      drawHorizontalBars(
        "chartTopVehicles",
        view.charts.topVehicles,
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
      drawHorizontalBars(
        "chartRideReviewScore",
        dashboard.pokrocilejsia_analytika.jazdy.chart,
        palette.accent2,
        (value) => formatNumber(value, 1) + " b."
      );
      drawDonutChart(
        "chartMaterialSegmentsAdvanced",
        dashboard.pokrocilejsia_analytika.material.chart,
        [palette.accent2, palette.accent3, palette.accent1, palette.accent4],
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

    document.querySelectorAll(".ride-toggle-btn").forEach((button) => {
      button.addEventListener("click", () => {
        setRideMode(button.dataset.rideMode === "valid");
      });
    });

    let resizeTimer = null;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(drawActiveTab, 120);
    });

    window.addEventListener("DOMContentLoaded", () => {
      setRideMode(true);
      drawActiveTab();
    });
  </script>
</body>
</html>
"""

    html = template
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
