from __future__ import annotations

from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "outputs"

JAZDY_INPUT = RAW_DIR / "dataset_jazdy_2024.xlsx"
MATERIAL_INPUT = RAW_DIR / "dataset_material_2023_2025.xlsx"
JAZDY_OUTPUT = OUT_DIR / "cleaned_jazdy.csv"
MATERIAL_OUTPUT = OUT_DIR / "cleaned_material.csv"

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


def clean_jazdy() -> pd.DataFrame:
    df = pd.read_excel(JAZDY_INPUT)

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

    cleaned.to_csv(JAZDY_OUTPUT, index=False)
    return cleaned


def clean_material() -> pd.DataFrame:
    df = pd.read_excel(MATERIAL_INPUT)

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
    material_totals["cumulative_share"] = material_totals["total_quantity"].cumsum() / material_totals["total_quantity"].sum()
    material_totals["abc_segment"] = material_totals["cumulative_share"].apply(classify_abc)

    cleaned = cleaned.merge(
        material_totals[["material_number", "abc_segment"]],
        on="material_number",
        how="left",
    )

    cleaned.to_csv(MATERIAL_OUTPUT, index=False)
    return cleaned


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    jazdy = clean_jazdy()
    material = clean_material()

    valid_trip_mask = ~jazdy["near_zero_trip"]

    print("Prepared outputs:")
    print(f"  {JAZDY_OUTPUT}")
    print(f"    rows: {len(jazdy)}")
    print(f"    vehicles: {jazdy['vehicle_id'].nunique()}")
    print(f"    near-zero trips: {int(jazdy['near_zero_trip'].sum())}")
    print(f"    potentially inefficient trips: {int(jazdy['potentially_inefficient_trip'].sum())}")
    print(f"    invalid coordinates: {int((~jazdy['coord_valid']).sum())}")
    print(f"    avg valid distance km: {jazdy.loc[valid_trip_mask, 'distance_km'].mean():.2f}")

    print(f"  {MATERIAL_OUTPUT}")
    print(f"    rows: {len(material)}")
    print(f"    materials: {material['material_number'].nunique()}")
    print(f"    prefixes: {material['material_prefix'].nunique()}")
    print(f"    total quantity: {material['quantity_clean'].sum():.0f}")
    print(f"    ABC A materials: {material.loc[material['abc_segment'] == 'A', 'material_number'].nunique()}")


if __name__ == "__main__":
    main()
