from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, time
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VIS_DIR = ROOT / "visualization"

JAZDY_INPUT = ROOT / "data" / "clean" / "dataset_jazdy_2024_cleaned.xlsx"
MATERIAL_INPUT = ROOT / "data" / "raw" / "dataset_material_2023_2025.xlsx"
HTML_OUTPUT = VIS_DIR / "analyza_dashboard.html"

TABLEAU_ABC_A_SHARE_THRESHOLD = 0.80
TABLEAU_ABC_B_SHARE_THRESHOLD = 0.95
TABLEAU_ABC_CHART_A_MIN_TOTAL_QUANTITY = 1_000_000
TABLEAU_ABC_CHART_B_MIN_TOTAL_QUANTITY = 100_000
TOP_MATERIAL_LIMIT = 10
RIDE_ANOMALY_DISTANCE_THRESHOLD_M = 500.0
RIDE_NUMERIC_ZERO_EPSILON = 1e-9
MOTOHOUR_SECONDS_PER_HOUR = 3600.0

EXPECTED_MATERIAL_ROW_COUNT = 644_106
EXPECTED_MATERIAL_UNIQUE_MATERIALS = 690
EXPECTED_MATERIAL_TOTAL_QUANTITY = 211_935_852.0
EXPECTED_MATERIAL_AVERAGE_QUANTITY = 329.0
EXPECTED_MATERIAL_MEDIAN_QUANTITY = 12.0
EXPECTED_MATERIAL_ZERO_ROWS = 172
EXPECTED_MATERIAL_PARSE_NAN_COUNT = 0
EXPECTED_MATERIAL_NEGATIVE_ROWS = 0
EXPECTED_MATERIAL_TOP_QUANTITY_MONTH = "2024-11"
EXPECTED_MATERIAL_TOP_QUANTITY_MONTH_VALUE = 16_738_491.0

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

RIDE_ANOMALY_CATEGORY_ORDER = [
    "Normálna jazda",
    "Pohyb bez motohodín",
    "Motor beží, auto stojí",
    "Nulová jazda (GPS ping)",
]

RIDE_ANOMALY_INTERPRETATIONS = {
    "Normálna jazda": "Motohodiny aj vzdialenosť naznačujú bežný presun bez zjavného signálu nekonzistencie.",
    "Pohyb bez motohodín": "Vozidlo sa pohlo aspoň 500 m, ale rozdiel motohodín je nulový. Môže ísť o telemetrický nesúlad, chýbajúci CAN, ťahanie alebo nekonzistentný záznam.",
    "Motor beží, auto stojí": "Motohodiny rastú, ale priamy posun ostáva pod 500 m. Môže ísť o nakládku, čakanie, hydrauliku, voľnobeh alebo inú stacionárnu prevádzku.",
    "Nulová jazda (GPS ping)": "Ani motohodiny, ani vzdialenosť nenaznačujú reálnu jazdu. Záznam skôr pripomína GPS/telemetrický ping.",
}

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

MATERIAL_MONTH_LABELS_COMPACT = {
    1: "Ja",
    2: "Fe",
    3: "Ma",
    4: "Ap",
    5: "My",
    6: "Jn",
    7: "Jl",
    8: "Au",
    9: "Se",
    10: "Oc",
    11: "No",
    12: "De",
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
        "description": "Kod materialu. Pouziva sa na DISTINCTCOUNT materialov, ABC segmentaciu aj rebricek top materialov.",
        "type": "STRING",
    },
    {
        "name": "MNOZSTVO",
        "description": "Parsed mnozstvo pohybu po Tableau-compatible integer coercion logike. Pouziva sa na mesacny objem, ABC aj top materialy.",
        "type": "DECIMAL",
    },
    {
        "name": "ABC_SEGMENT",
        "description": "Odvodena ABC segmentacia podla kumulativneho podielu na celkovom objeme materialov: A do 80 %, B do 95 %, C zvysok.",
        "type": "CATEGORY",
    },
]


def _normalize_material_quantity_text(value: object) -> str:
    return (
        str(value)
        .strip()
        .replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\u2007", " ")
    )


def parse_material_quantity_tableau(value: object) -> int | float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, bool):
        raise ValueError(f"Boolean quantity is not supported: {value!r}")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return np.nan
        numeric = float(value)
        if numeric.is_integer():
            return int(numeric)
        raise ValueError(
            "Non-integral numeric MNOZSTVO encountered in a column Tableau typed as integer: "
            f"{value!r}"
        )

    text = _normalize_material_quantity_text(value)
    if not text:
        return np.nan

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()

    if text.endswith("-"):
        negative = True
        text = text[:-1].strip()

    if text.startswith("−"):
        negative = True
        text = text[1:].strip()
    elif text.startswith("-"):
        negative = True
        text = text[1:].strip()
    elif text.startswith("+"):
        text = text[1:].strip()

    text = text.replace(" ", "").replace(",", "").replace(".", "")
    if not text or not text.isdigit():
        raise ValueError(f"Unable to parse MNOZSTVO value {value!r} with Tableau-style integer coercion.")

    numeric = int(text)
    return -numeric if negative else numeric


def parse_material_quantity_series(
    raw_values: pd.Series,
    *,
    source_path: Path | None = None,
    print_debug: bool = True,
) -> tuple[pd.Series, dict[str, object]]:
    parsed_values: list[object] = []
    parse_fail_examples: list[dict[str, object]] = []

    for row_idx, value in raw_values.items():
        try:
            parsed_values.append(parse_material_quantity_tableau(value))
        except ValueError as exc:
            parsed_values.append(np.nan)
            if len(parse_fail_examples) < 10:
                parse_fail_examples.append(
                    {
                        "row_number": int(row_idx) + 2,
                        "raw_value": value,
                        "error": str(exc),
                    }
                )

    parsed_series = pd.to_numeric(pd.Series(parsed_values, index=raw_values.index), errors="coerce")
    report = {
        "source_path": str(source_path) if source_path else None,
        "row_count": int(len(raw_values)),
        "parse_nan_count": int(parsed_series.isna().sum()),
        "negative_count": int((parsed_series < 0).sum()),
        "signed_sum": float(parsed_series.sum()),
        "average": float(parsed_series.mean()),
        "parse_fail_examples": parse_fail_examples,
    }

    if print_debug:
        source_text = f" source={report['source_path']}" if report["source_path"] else ""
        print(
            "Material parse summary:"
            f"{source_text}"
            f" rows={report['row_count']}"
            f" parse_nan_count={report['parse_nan_count']}"
            f" negative_rows={report['negative_count']}"
            f" signed_total={report['signed_sum']:.1f}"
            f" average={report['average']:.1f}"
        )

    if report["parse_nan_count"] > 0:
        sample_rows = ", ".join(
            f"row {failure['row_number']}" for failure in parse_fail_examples[:5]
        )
        raise ValueError(
            "Hard failure: non-empty MNOZSTVO values could not be parsed with Tableau parity logic. "
            f"First failures: {sample_rows or 'n/a'}."
        )

    return parsed_series, report


def normalize_column_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_text.lower())


def normalize_join_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", "", ascii_text.upper())


def parse_lookup_numeric(value: object) -> float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)

    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return np.nan

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return np.nan


def classify_material_abc_by_cumulative_share(cumulative_share: float) -> str:
    if cumulative_share <= TABLEAU_ABC_A_SHARE_THRESHOLD:
        return "A"
    if cumulative_share <= TABLEAU_ABC_B_SHARE_THRESHOLD:
        return "B"
    return "C"


def classify_material_abc_for_count_chart(total_quantity: float) -> str:
    if total_quantity >= TABLEAU_ABC_CHART_A_MIN_TOTAL_QUANTITY:
        return "A"
    if total_quantity >= TABLEAU_ABC_CHART_B_MIN_TOTAL_QUANTITY:
        return "B"
    return "C"


def aggregate_material_totals(material: pd.DataFrame) -> pd.DataFrame:
    totals = (
        material.groupby("material_number", as_index=False)
        .agg(
            total_quantity=("quantity_signed", "sum"),
            average_quantity=("quantity_signed", "mean"),
        )
        .sort_values(["total_quantity", "material_number"], ascending=[False, True])
        .reset_index(drop=True)
    )
    overall_total = float(totals["total_quantity"].sum())
    if overall_total:
        totals["cumulative_share"] = totals["total_quantity"].cumsum() / overall_total
    else:
        totals["cumulative_share"] = 0.0
    totals["abc_segment"] = totals["cumulative_share"].apply(classify_material_abc_by_cumulative_share)
    totals["quantity_share_pct"] = (
        totals["total_quantity"] / overall_total * 100 if overall_total else 0.0
    )
    return totals


def finalize_material_dataset(cleaned: pd.DataFrame, *, report_parse: bool = True) -> pd.DataFrame:
    cleaned = cleaned.copy()

    if "quantity_signed" in cleaned.columns:
        quantity_signed = pd.to_numeric(cleaned["quantity_signed"], errors="coerce")
    elif "quantity_clean" in cleaned.columns:
        quantity_signed = pd.to_numeric(cleaned["quantity_clean"], errors="coerce")
    else:
        raise ValueError("Material dataset is missing quantity_signed / quantity_clean.")

    parse_nan_count = int(quantity_signed.isna().sum())
    if report_parse:
        print(f"Material quantity parse NaNs: {parse_nan_count} of {len(cleaned)}")
    if parse_nan_count > 0:
        raise ValueError(
            "Hard failure: material dataset contains NaN quantity_signed values after parsing. "
            f"NaN count: {parse_nan_count}."
        )

    cleaned["quantity_signed"] = quantity_signed
    cleaned["quantity_abs"] = quantity_signed.abs()
    cleaned["zero_quantity_record"] = cleaned["quantity_signed"] == 0
    cleaned["movement_direction"] = np.select(
        [
            cleaned["quantity_signed"] > 0,
            cleaned["quantity_signed"] < 0,
            cleaned["quantity_signed"] == 0,
        ],
        [
            "positive",
            "negative",
            "zero",
        ],
        default="zero",
    )
    cleaned = cleaned.drop(columns=["quantity_clean", "abc_segment"], errors="ignore")

    material_totals = aggregate_material_totals(cleaned)

    finalized = cleaned.merge(
        material_totals[["material_number", "abc_segment"]],
        on="material_number",
        how="left",
    )
    missing_abc_count = int(finalized["abc_segment"].isna().sum())
    if missing_abc_count:
        raise AssertionError(f"ABC segment merge produced missing values: {missing_abc_count}")
    return finalized


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


def parse_material_date_tableau(value: object) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()

    if isinstance(value, datetime):
        # The material DATUM column is mixed in the workbook source file:
        # rows with ambiguous day<=12 were auto-coerced into native Excel dates,
        # while the rest stayed as day-first text. Tableau parity is restored only
        # when the native-date subset is reinterpreted with swapped day/month.
        return pd.Timestamp(
            year=value.year,
            month=value.day,
            day=value.month,
            hour=value.hour,
            minute=value.minute,
            second=value.second,
        )

    return parse_mixed_date(
        value,
        [
            "%d. %m. %Y %H:%M:%S",
            "%d.%m.%Y %H:%M:%S",
            "%d. %m. %Y %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ],
    )


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


def json_number_or_none(value: object) -> float | int | None:
    if pd.isna(value):
        return None
    numeric = float(value)
    if numeric.is_integer():
        return int(numeric)
    return numeric


def load_jazdy_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError(f"Unsupported rides input format: {path}. Expected Excel workbook.")

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

    tableau_lat_start = pd.to_numeric(df["EW_START"], errors="coerce") / 1_000_000
    tableau_lon_start = pd.to_numeric(df["EL_START"], errors="coerce") / 1_000_000
    distance_m = pd.to_numeric(df["DIST_START_END_M"], errors="coerce") / 1e9
    distance_km = distance_m / 1000
    motohour_start_raw = pd.to_numeric(df["MOTOHODINY_ZACIATOK"], errors="coerce")
    motohour_end_raw = pd.to_numeric(df["MOTOHODINY_KONIEC"], errors="coerce")
    motohour_diff_raw = pd.to_numeric(df["ROZDIEL_MOTOHODINY"], errors="coerce")

    motohour_comparison_mask = (
        motohour_start_raw.notna()
        & motohour_end_raw.notna()
        & motohour_diff_raw.notna()
    )
    motohour_delta_mismatch = (
        (motohour_end_raw - motohour_start_raw - motohour_diff_raw).abs() > RIDE_NUMERIC_ZERO_EPSILON
    ) & motohour_comparison_mask
    motohour_mismatch_count = int(motohour_delta_mismatch.sum())
    if motohour_mismatch_count:
        raise ValueError(
            "MOTOHODINY_ZACIATOK / MOTOHODINY_KONIEC do not match ROZDIEL_MOTOHODINY "
            f"for {motohour_mismatch_count} ride rows."
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
            "motohour_start_raw": motohour_start_raw,
            "motohour_end_raw": motohour_end_raw,
            "motohour_diff_raw": motohour_diff_raw,
            "motohour_diff_hours": motohour_diff_raw / MOTOHOUR_SECONDS_PER_HOUR,
            "ew_start_raw": pd.to_numeric(df["EW_START"], errors="coerce"),
            "el_start_raw": pd.to_numeric(df["EL_START"], errors="coerce"),
            "tableau_valid_trip": tableau_valid_trip,
            "ride_category_tableau": distance_m.apply(classify_tableau_ride_category),
        }
    )

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
    if path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError(f"Unsupported material input format: {path}. Expected Excel workbook.")

    df = pd.read_excel(path)
    quantity_signed, _ = parse_material_quantity_series(
        df["MNOZSTVO"],
        source_path=path,
        print_debug=True,
    )
    df["movement_dt"] = df["DATUM"].apply(parse_material_date_tableau)

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
            "quantity_signed": quantity_signed,
        }
    )
    return finalize_material_dataset(cleaned, report_parse=False)


def summarize_material_quantity_validation(material: pd.DataFrame) -> dict:
    quantity_signed = material["quantity_signed"]
    quantity_abs = material["quantity_abs"]
    signed_total_quantity = float(quantity_signed.sum())
    abs_total_quantity = float(quantity_abs.sum())

    return {
        "signed_total_quantity": round(signed_total_quantity, 1),
        "abs_total_quantity": round(abs_total_quantity, 1),
        "positive_total_quantity": round(float(quantity_signed.loc[quantity_signed > 0].sum()), 1),
        "negative_total_quantity_abs": round(float(quantity_signed.loc[quantity_signed < 0].abs().sum()), 1),
        "negative_row_count": int((quantity_signed < 0).sum()),
        "zero_row_count": int(material["zero_quantity_record"].sum()),
        "parse_nan_count": int(quantity_signed.isna().sum()),
        "abs_minus_signed_difference": round(abs_total_quantity - signed_total_quantity, 1),
    }


def assert_exact(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise AssertionError(f"{name} mismatch: expected {expected!r}, got {actual!r}")


def assert_close(name: str, actual: float, expected: float, tolerance: float = 1e-9) -> None:
    if abs(float(actual) - float(expected)) > tolerance:
        raise AssertionError(f"{name} mismatch: expected {expected!r}, got {actual!r}")


def verify_material_monthly(material: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    material_monthly = (
        material.groupby("year_month", as_index=False)
        .agg(
            unique_material_count=("material_number", "nunique"),
            total_quantity=("quantity_signed", "sum"),
        )
        .sort_values("year_month")
        .reset_index(drop=True)
    )

    total_quantity_sum = float(material_monthly["total_quantity"].sum())
    top_quantity_month = material_monthly.sort_values(
        ["total_quantity", "year_month"],
        ascending=[False, True],
    ).iloc[0]

    assert_close("monthly total_quantity sum", total_quantity_sum, EXPECTED_MATERIAL_TOTAL_QUANTITY)
    assert_exact("max monthly total_quantity month", top_quantity_month.year_month, EXPECTED_MATERIAL_TOP_QUANTITY_MONTH)
    assert_close(
        "max monthly total_quantity value",
        float(top_quantity_month.total_quantity),
        EXPECTED_MATERIAL_TOP_QUANTITY_MONTH_VALUE,
    )

    return material_monthly, {
        "total_quantity_sum": total_quantity_sum,
        "top_quantity_month": str(top_quantity_month.year_month),
        "top_quantity_month_value": float(top_quantity_month.total_quantity),
    }


def verify_material_abc(material_totals: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    if material_totals.empty:
        raise AssertionError("Material totals are empty.")

    missing_segment_count = int(material_totals["abc_segment"].isna().sum())
    assert_exact("missing abc_segment count", missing_segment_count, 0)

    total_material_count = int(material_totals["material_number"].nunique())
    total_quantity = float(material_totals["total_quantity"].sum())

    abc_summary = (
        material_totals.groupby("abc_segment", as_index=False)
        .agg(
            unique_material_count=("material_number", "nunique"),
            total_quantity=("total_quantity", "sum"),
        )
        .sort_values("abc_segment")
        .reset_index(drop=True)
    )
    abc_summary["quantity_share_pct"] = (
        abc_summary["total_quantity"] / total_quantity * 100 if total_quantity else 0.0
    ).round(1)
    abc_summary["material_share_pct"] = (
        abc_summary["unique_material_count"] / total_material_count * 100 if total_material_count else 0.0
    ).round(1)

    unique_material_sum = int(abc_summary["unique_material_count"].sum())
    assert_exact("ABC unique material sum", unique_material_sum, EXPECTED_MATERIAL_UNIQUE_MATERIALS)

    segment_counts = {segment: 0 for segment in ["A", "B", "C"]}
    segment_counts.update(
        {
            row.abc_segment: int(row.unique_material_count)
            for row in abc_summary.itertuples(index=False)
        }
    )

    return abc_summary, {
        "unique_material_sum": unique_material_sum,
        "missing_segment_count": missing_segment_count,
        "segment_counts": segment_counts,
    }


def build_material_abc_count_chart(material_totals: pd.DataFrame) -> list[dict[str, int]]:
    segment_counts = {segment: 0 for segment in ["A", "B", "C"]}
    chart_segments = material_totals["total_quantity"].apply(classify_material_abc_for_count_chart)
    segment_counts.update(chart_segments.value_counts().to_dict())
    return [
        {"label": segment, "value": int(segment_counts[segment])}
        for segment in ["A", "B", "C"]
    ]


def find_material_lookup_file(root: Path) -> Path | None:
    candidates = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".xlsx", ".xls"}
        and normalize_column_name(path.stem) == "regcisciselnik"
    )
    return candidates[0] if candidates else None


def load_material_lookup(root: Path) -> dict[str, object]:
    lookup_path = find_material_lookup_file(root)
    if lookup_path is None:
        return {
            "found": False,
            "usable": False,
            "path": None,
            "matched_material_count": 0,
            "joined": pd.DataFrame(),
        }

    lookup_raw = pd.read_excel(lookup_path)
    normalized_columns = {column: normalize_column_name(column) for column in lookup_raw.columns}

    reg_col = next(
        (
            column
            for column, normalized in normalized_columns.items()
            if normalized in {"regcis", "regc", "regcismaterialu"}
        ),
        None,
    )
    name_col = next(
        (
            column
            for column, normalized in normalized_columns.items()
            if normalized in {"nazev", "nazov", "materialname", "name"}
        ),
        None,
    )
    min_col = next(
        (
            column
            for column, normalized in normalized_columns.items()
            if normalized in {"minimumskladu", "minskladu", "minimumskladu", "minimum", "minstock"}
        ),
        None,
    )

    if reg_col is None or min_col is None:
        return {
            "found": True,
            "usable": False,
            "path": lookup_path,
            "matched_material_count": 0,
            "joined": pd.DataFrame(),
        }

    lookup = lookup_raw.copy()
    lookup["reg_cis_norm"] = lookup[reg_col].apply(normalize_join_text)
    lookup = lookup.loc[lookup["reg_cis_norm"] != ""].copy()
    lookup["minimum_stock"] = lookup[min_col].apply(parse_lookup_numeric)
    lookup["material_name"] = (
        lookup[name_col].astype(str).str.strip().where(lookup[name_col].notna(), "")
        if name_col
        else ""
    )

    lookup_keys = []
    for row in lookup.itertuples(index=False):
        reg_cis_norm = row.reg_cis_norm
        candidate_keys = {
            reg_cis_norm,
            f"MAT07{reg_cis_norm}",
        }
        if not reg_cis_norm.startswith("MAT"):
            candidate_keys.add(f"MAT{reg_cis_norm}")
        for join_key in sorted(candidate_keys):
            lookup_keys.append(
                {
                    "join_key": join_key,
                    "material_name": row.material_name if isinstance(row.material_name, str) else "",
                    "minimum_stock": float(row.minimum_stock) if not pd.isna(row.minimum_stock) else np.nan,
                }
            )

    joined_lookup = (
        pd.DataFrame(lookup_keys)
        .sort_values(["join_key", "material_name"])
        .drop_duplicates("join_key")
        .reset_index(drop=True)
    )

    return {
        "found": True,
        "usable": True,
        "path": lookup_path,
        "matched_material_count": 0,
        "joined": joined_lookup,
    }


def attach_material_lookup(material_totals: pd.DataFrame, root: Path) -> dict[str, object]:
    lookup_meta = load_material_lookup(root)
    material_totals_named = material_totals.copy()
    material_totals_named["join_key"] = material_totals_named["material_number"].apply(normalize_join_text)
    material_totals_named["material_name"] = ""
    material_totals_named["minimum_stock"] = np.nan

    if lookup_meta["usable"]:
        material_totals_named = material_totals_named.merge(
            lookup_meta["joined"],
            on="join_key",
            how="left",
            suffixes=("", "_lookup"),
        )
        if "material_name_lookup" in material_totals_named.columns:
            material_totals_named["material_name"] = (
                material_totals_named["material_name_lookup"].fillna("").astype(str).str.strip()
            )
            material_totals_named = material_totals_named.drop(columns=["material_name_lookup"])
        if "minimum_stock_lookup" in material_totals_named.columns:
            material_totals_named["minimum_stock"] = pd.to_numeric(
                material_totals_named["minimum_stock_lookup"], errors="coerce"
            )
            material_totals_named = material_totals_named.drop(columns=["minimum_stock_lookup"])
        lookup_meta["matched_material_count"] = int(material_totals_named["minimum_stock"].notna().sum())

    material_totals_named["display_label"] = np.where(
        material_totals_named["material_name"].astype(str).str.strip() != "",
        material_totals_named["material_name"].astype(str).str.strip(),
        material_totals_named["material_number"],
    )
    return {
        **lookup_meta,
        "material_totals": material_totals_named,
    }


def compute_stock_minimum_comparison(material_totals_named: pd.DataFrame) -> pd.DataFrame:
    if material_totals_named.empty or "minimum_stock" not in material_totals_named.columns:
        return pd.DataFrame()

    comparison = material_totals_named.loc[material_totals_named["minimum_stock"].notna()].copy()
    if comparison.empty:
        return comparison

    comparison["difference"] = comparison["minimum_stock"] - comparison["average_quantity"]
    comparison = comparison.loc[comparison["difference"] > 0].copy()
    if comparison.empty:
        return comparison

    return (
        comparison.sort_values(["difference", "material_number"], ascending=[False, True])
        .head(TOP_MATERIAL_LIMIT)
        .reset_index(drop=True)
    )


def build_material_views(material: pd.DataFrame) -> dict[str, object]:
    material_validation = summarize_material_quantity_validation(material)
    material_totals = aggregate_material_totals(material)
    material_lookup = attach_material_lookup(material_totals, ROOT)
    material_totals_named = material_lookup["material_totals"]

    kpi_summary = {
        "total_rows": int(len(material)),
        "unique_materials": int(material["material_number"].nunique()),
        "total_quantity": float(material["quantity_signed"].sum()),
        "average_quantity": round(float(material["quantity_signed"].mean()), 1),
        "median_quantity": round(float(material["quantity_signed"].median()), 1),
        "zero_rows": int(material["zero_quantity_record"].sum()),
        "parse_nan_count": int(material_validation["parse_nan_count"]),
        "negative_rows": int(material_validation["negative_row_count"]),
    }
    assert_exact("material total movement rows", kpi_summary["total_rows"], EXPECTED_MATERIAL_ROW_COUNT)
    assert_exact("material unique materials", kpi_summary["unique_materials"], EXPECTED_MATERIAL_UNIQUE_MATERIALS)
    assert_close("material total quantity", kpi_summary["total_quantity"], EXPECTED_MATERIAL_TOTAL_QUANTITY)
    assert_close("material average quantity", kpi_summary["average_quantity"], EXPECTED_MATERIAL_AVERAGE_QUANTITY)
    assert_close("material median quantity", kpi_summary["median_quantity"], EXPECTED_MATERIAL_MEDIAN_QUANTITY)
    assert_exact("material zero quantity rows", kpi_summary["zero_rows"], EXPECTED_MATERIAL_ZERO_ROWS)
    assert_exact("material parse NaN count", kpi_summary["parse_nan_count"], EXPECTED_MATERIAL_PARSE_NAN_COUNT)
    assert_exact("material negative row count", kpi_summary["negative_rows"], EXPECTED_MATERIAL_NEGATIVE_ROWS)

    material_monthly, monthly_summary = verify_material_monthly(material)
    abc_summary, abc_verification = verify_material_abc(material_totals)

    top_materials = material_totals_named.head(TOP_MATERIAL_LIMIT).copy()
    comparison_chart = compute_stock_minimum_comparison(material_totals_named)

    return {
        "validation": material_validation,
        "kpi_summary": kpi_summary,
        "material_monthly": material_monthly,
        "monthly_summary": monthly_summary,
        "abc_summary": abc_summary,
        "abc_verification": abc_verification,
        "material_totals": material_totals_named,
        "top_materials": top_materials,
        "lookup": {
            "found": bool(material_lookup["found"]),
            "usable": bool(material_lookup["usable"]),
            "path": str(material_lookup["path"]) if material_lookup["path"] else None,
            "matched_material_count": int(material_lookup["matched_material_count"]),
        },
        "comparison_chart": comparison_chart,
        "comparison_chart_generated": bool(not comparison_chart.empty),
    }


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


def material_month_label_compact(value: str) -> str:
    year, month = value.split("-")
    return f"{MATERIAL_MONTH_LABELS_COMPACT.get(int(month), month)}{year[2:]}"


def material_month_label_full(value: str) -> str:
    year, month = value.split("-")
    return f"{MONTH_NAMES_SK.get(int(month), month).capitalize()} {year}"


def compute_advanced_ride_analytics(jazdy: pd.DataFrame, trips_per_vehicle: pd.DataFrame) -> dict:
    ride_signals = jazdy.copy()
    motohour_diff_raw = pd.to_numeric(ride_signals["motohour_diff_raw"], errors="coerce")
    distance_m = pd.to_numeric(ride_signals["distance_m"], errors="coerce")

    missing_motohour_count = int(motohour_diff_raw.isna().sum())
    missing_distance_count = int(distance_m.isna().sum())
    if missing_motohour_count or missing_distance_count:
        raise ValueError(
            "Advanced ride anomaly analysis requires non-null motohour and distance signals. "
            f"Missing motohours={missing_motohour_count}, missing distance={missing_distance_count}."
        )

    # Excel-backed numeric fields can arrive as floats, so zero is interpreted with a tiny epsilon
    # before the rules separate true movement from a telemetry-only ping.
    motohour_zero = motohour_diff_raw.abs() <= RIDE_NUMERIC_ZERO_EPSILON
    motohour_positive = motohour_diff_raw > RIDE_NUMERIC_ZERO_EPSILON
    near_zero_movement = distance_m < RIDE_ANOMALY_DISTANCE_THRESHOLD_M

    ride_signals["anomaly_category"] = np.select(
        [
            motohour_positive & near_zero_movement,
            motohour_zero & (~near_zero_movement),
            motohour_zero & near_zero_movement,
        ],
        [
            "Motor beží, auto stojí",
            "Pohyb bez motohodín",
            "Nulová jazda (GPS ping)",
        ],
        default="Normálna jazda",
    )
    ride_signals["anomalous_trip"] = ride_signals["anomaly_category"] != "Normálna jazda"
    ride_signals["idle_motohour_hours"] = np.where(
        ride_signals["anomaly_category"] == "Motor beží, auto stojí",
        motohour_diff_raw / MOTOHOUR_SECONDS_PER_HOUR,
        0.0,
    )

    category_order = {name: index for index, name in enumerate(RIDE_ANOMALY_CATEGORY_ORDER)}
    total_analyzed_rides = int(len(ride_signals))
    category_summary = (
        ride_signals["anomaly_category"]
        .value_counts()
        .reindex(RIDE_ANOMALY_CATEGORY_ORDER, fill_value=0)
        .rename_axis("category")
        .reset_index(name="trip_count")
    )
    category_summary["share_pct"] = (
        category_summary["trip_count"] / total_analyzed_rides * 100 if total_analyzed_rides else 0.0
    )

    category_total_count = int(category_summary["trip_count"].sum())
    category_share_pct_sum = float(category_summary["share_pct"].sum())
    assert_exact("ride anomaly category total", category_total_count, total_analyzed_rides)
    assert_close(
        "ride anomaly category share pct sum",
        category_share_pct_sum,
        100.0 if total_analyzed_rides else 0.0,
        tolerance=1e-6,
    )

    anomaly_summary = category_summary.loc[category_summary["category"] != "Normálna jazda"].copy()
    anomaly_summary["category_order"] = anomaly_summary["category"].map(category_order)
    anomaly_summary = anomaly_summary.sort_values(
        ["trip_count", "category_order"],
        ascending=[False, True],
    )

    total_anomalous_rides = int(anomaly_summary["trip_count"].sum())
    anomaly_share_pct = total_anomalous_rides / total_analyzed_rides * 100 if total_analyzed_rides else 0.0
    total_idle_motohour_hours = float(ride_signals["idle_motohour_hours"].sum())
    top_anomaly = anomaly_summary.iloc[0]

    vehicle_review = (
        ride_signals.groupby("vehicle_id", as_index=False)
        .agg(
            trip_count=("vehicle_id", "size"),
            motor_running_stationary_count=("anomaly_category", lambda s: int((s == "Motor beží, auto stojí").sum())),
            movement_without_motohours_count=("anomaly_category", lambda s: int((s == "Pohyb bez motohodín").sum())),
            gps_ping_count=("anomaly_category", lambda s: int((s == "Nulová jazda (GPS ping)").sum())),
            anomalous_trip_count=("anomalous_trip", "sum"),
            motor_running_stationary_motohours=("idle_motohour_hours", "sum"),
        )
        .sort_values("vehicle_id")
        .reset_index(drop=True)
    )
    vehicle_review["anomalous_share_pct"] = (
        vehicle_review["anomalous_trip_count"] / vehicle_review["trip_count"] * 100
    )
    vehicle_review["motor_running_stationary_share_pct"] = (
        vehicle_review["motor_running_stationary_count"] / vehicle_review["trip_count"] * 100
    )
    vehicle_review = vehicle_review.sort_values(
        [
            "anomalous_share_pct",
            "motor_running_stationary_motohours",
            "motor_running_stationary_count",
            "vehicle_id",
        ],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)

    top_motor_concentration_vehicle = vehicle_review.sort_values(
        [
            "motor_running_stationary_share_pct",
            "motor_running_stationary_count",
            "motor_running_stationary_motohours",
            "vehicle_id",
        ],
        ascending=[False, False, False, True],
    ).iloc[0]
    top_movement_without_motohours_vehicle = vehicle_review.sort_values(
        [
            "movement_without_motohours_count",
            "anomalous_share_pct",
            "vehicle_id",
        ],
        ascending=[False, False, True],
    ).iloc[0]

    count_by_category = {
        row.category: int(row.trip_count)
        for row in category_summary.itertuples(index=False)
    }

    return {
        "title": "Pokročilá analytika: anomálie medzi motohodinami a vzdialenosťou",
        "question": (
            "Ktoré jazdy naznačujú neefektívnu prevádzku, státie s bežiacim motorom "
            "alebo GPS/telemetrickú nekonzistenciu?"
        ),
        "method_title": "Heuristická kategorizácia z polí ROZDIEL_MOTOHODINY a DIST_START_END_M",
        "method_intro": (
            "Každá jazda sa zaradí presne do jednej kategórie podľa rozdielu motohodín a priamej "
            "vzdialenosti medzi štartom a koncom. Výstup je podklad na interpretáciu a manuálny review, "
            "nie automatický dôkaz prevádzkového problému."
        ),
        "method_points": [
            f"Hranica pre minimálny pohyb je {int(RIDE_ANOMALY_DISTANCE_THRESHOLD_M)} m. Jazdy pod týmto prahom sa čítajú ako near-zero presun.",
            "Nulová hodnota motohodín sa vyhodnocuje s malým epsilon, aby sa odfiltrovali čisto numerické artefakty po načítaní Excelu.",
            "Kategória Motor beží, auto stojí môže znamenať nakládku, čakanie, hydrauliku, voľnobeh alebo inú stacionárnu prevádzku.",
            "Kategória Pohyb bez motohodín môže ukazovať telemetrický nesúlad, chýbajúci CAN, ťahanie alebo nekonzistentný záznam.",
        ],
        "summary_cards": [
            {
                "label": "Analyzované jazdy",
                "value": total_analyzed_rides,
                "sub": "plná populácia Datasetu 1",
                "format": "int",
            },
            {
                "label": "Anomálne jazdy",
                "value": total_anomalous_rides,
                "sub": "súčet troch anomálnych kategórií",
                "format": "int",
            },
            {
                "label": "Podiel anomálií",
                "value": round(anomaly_share_pct, 1),
                "sub": "anomálne jazdy / všetky analyzované jazdy",
                "format": "pct1",
            },
            {
                "label": "Motohodiny pri státí (h)",
                "value": round(total_idle_motohour_hours, 1),
                "sub": "súčet kategórie Motor beží, auto stojí",
                "format": "float1",
            },
            {
                "label": "Najčastejšia anomália",
                "value": int(top_anomaly.trip_count),
                "sub": f"{top_anomaly.category} | {top_anomaly.share_pct:.1f} %",
                "format": "int",
            },
        ],
        "chart": [
            {
                "label": row.category,
                "value": int(row.trip_count),
            }
            for row in category_summary.itertuples(index=False)
        ],
        "category_table": [
            {
                "category": row.category,
                "trip_count": int(row.trip_count),
                "share_pct": float(row.share_pct),
                "interpretation": RIDE_ANOMALY_INTERPRETATIONS[row.category],
            }
            for row in category_summary.itertuples(index=False)
        ],
        "category_table_intro": (
            "Každá jazda patrí presne do jednej zo štyroch kategórií, takže počty aj podiely sa skladajú "
            "na celú analyzovanú populáciu jázd."
        ),
        "key_findings": [
            (
                "Rozdelenie kategórií: "
                f"Normálna jazda {count_by_category['Normálna jazda']}, "
                f"Pohyb bez motohodín {count_by_category['Pohyb bez motohodín']}, "
                f"Motor beží, auto stojí {count_by_category['Motor beží, auto stojí']}, "
                f"Nulová jazda (GPS ping) {count_by_category['Nulová jazda (GPS ping)']}."
            ),
            (
                f"Najsilnejší anomálny signál je {top_anomaly.category} "
                f"({int(top_anomaly.trip_count)} jázd; {top_anomaly.share_pct:.1f} % všetkých jázd)."
            ),
            (
                f"V kategórii Motor beží, auto stojí sa nazbieralo {total_idle_motohour_hours:.1f} motohodín. "
                f"Najvyššiu koncentráciu má vozidlo {top_motor_concentration_vehicle.vehicle_id} "
                f"({int(top_motor_concentration_vehicle.motor_running_stationary_count)} jázd; "
                f"{top_motor_concentration_vehicle.motor_running_stationary_share_pct:.1f} % jeho jázd)."
            ),
            (
                f"Najvyšší počet kategórie Pohyb bez motohodín má vozidlo "
                f"{top_movement_without_motohours_vehicle.vehicle_id} "
                f"({int(top_movement_without_motohours_vehicle.movement_without_motohours_count)} jázd)."
            ),
        ],
        "vehicle_review": [
            {
                "vehicle_id": row.vehicle_id,
                "trip_count": int(row.trip_count),
                "motor_running_stationary_count": int(row.motor_running_stationary_count),
                "movement_without_motohours_count": int(row.movement_without_motohours_count),
                "gps_ping_count": int(row.gps_ping_count),
                "anomalous_share_pct": float(row.anomalous_share_pct),
                "motor_running_stationary_motohours": float(row.motor_running_stationary_motohours),
            }
            for row in vehicle_review.itertuples(index=False)
        ],
        "vehicle_review_intro": (
            "Tabuľka je zoradená podľa podielu anomálnych jázd, pri zhode podľa motohodín v kategórii "
            "Motor beží, auto stojí. Každý riadok používa iba metriky odvodené z nového 4-kategóriového rámca."
        ),
        "validation": {
            "analyzed_ride_count": total_analyzed_rides,
            "category_total_count": category_total_count,
            "category_share_pct_sum": category_share_pct_sum,
            "anomaly_ride_count": total_anomalous_rides,
            "anomaly_share_pct": anomaly_share_pct,
            "distance_threshold_m": RIDE_ANOMALY_DISTANCE_THRESHOLD_M,
            "zero_epsilon": RIDE_NUMERIC_ZERO_EPSILON,
            "category_counts": count_by_category,
            "motor_running_stationary_motohours": total_idle_motohour_hours,
        },
    }


def compute_advanced_material_analytics(material_views: dict[str, object]) -> dict:
    abc_summary = material_views["abc_summary"]
    top_materials = material_views["top_materials"]
    material_totals = material_views["material_totals"]
    comparison_chart = material_views["comparison_chart"]
    lookup_info = material_views["lookup"]
    total_quantity = float(material_views["kpi_summary"]["total_quantity"])

    top_material = top_materials.iloc[0]
    top10_share_pct = round(float(top_materials["total_quantity"].sum() / total_quantity * 100), 1) if total_quantity else 0.0
    deficit_candidates = pd.DataFrame()
    if "minimum_stock" in material_totals.columns:
        deficit_candidates = material_totals.loc[material_totals["minimum_stock"].notna()].copy()
        if not deficit_candidates.empty:
            deficit_candidates["difference"] = deficit_candidates["minimum_stock"] - deficit_candidates["average_quantity"]
            deficit_candidates = deficit_candidates.loc[deficit_candidates["difference"] > 0].copy()

    a_segment = abc_summary.loc[abc_summary["abc_segment"] == "A"]
    a_segment_count = int(a_segment["unique_material_count"].iloc[0]) if not a_segment.empty else 0
    deficit_count = int(len(deficit_candidates))
    matched_material_count = int(lookup_info["matched_material_count"])

    detail_rows = []
    detail_headers = ["Materiál", "MAT_NR", "ABC", "Celkové množstvo", "Podiel množstva", "Priemerné množstvo"]
    detail_title = "Top materiály podľa objemu"
    detail_intro = "Top 10 materiálov vychádza zo súčtu parsed quantity podľa MAT_NR. Ak je dostupný lookup, názov materiálu nahrádza kód."
    for row in top_materials.itertuples(index=False):
        detail_rows.append(
            {
                "label": row.display_label,
                "material_number": row.material_number,
                "abc_segment": row.abc_segment,
                "total_quantity": float(row.total_quantity),
                "quantity_share_pct": float(row.quantity_share_pct),
                "average_quantity": float(row.average_quantity),
            }
        )

    if not comparison_chart.empty:
        detail_headers = ["Materiál", "MAT_NR", "Minimum skladu", "Priemerné množstvo", "Deficit", "ABC"]
        detail_title = "Materiály pod minimom skladu"
        detail_intro = "Tabuľka ukazuje najväčšie deficity podľa rozdielu Minimum skladu - priemerné množstvo."
        detail_rows = [
            {
                "label": row.display_label,
                "material_number": row.material_number,
                "minimum_stock": float(row.minimum_stock),
                "average_quantity": float(row.average_quantity),
                "difference": float(row.difference),
                "abc_segment": row.abc_segment,
            }
            for row in comparison_chart.itertuples(index=False)
        ]

    return {
        "question": "Ako sa celkový objem rozdeľuje medzi ABC segmenty a ktoré materiály nesú najväčší objem alebo deficit voči minimu skladu?",
        "method_title": "Kumulatívna ABC segmentácia a rebríček materiálov podľa objemu",
        "method_points": [
            "Najprv sa pre každý MAT_NR spočíta celkové parsed množstvo a zoradí sa zostupne.",
            "ABC segment vzniká z kumulatívneho podielu na celkovom objeme: A do 80 %, B do 95 %, C zvyšok.",
            "Ak je dostupný RegCis lookup, názov materiálu nahrádza MAT_NR a navyše sa počíta deficit Minimum skladu - priemerné množstvo.",
        ],
        "summary_cards": [
            {
                "label": "Materiály v segmente A",
                "value": a_segment_count,
                "sub": "kumulatívne kryjú prvých 80 % objemu",
                "format": "int",
            },
            {
                "label": "Top 10 podiel objemu",
                "value": top10_share_pct,
                "sub": "podiel top 10 materiálov na celkovom objeme",
                "format": "pct1",
            },
            {
                "label": "Materiály pod minimom",
                "value": deficit_count,
                "sub": (
                    f"z {matched_material_count} materialov s lookupom"
                    if lookup_info["found"] and lookup_info["usable"]
                    else "lookup minima sa nenasiel"
                ),
                "format": "int",
            },
        ],
        "chart": [
            {
                "label": row.abc_segment,
                "value": float(row.quantity_share_pct),
            }
            for row in abc_summary.itertuples(index=False)
        ],
        "chart_title": "Podiel objemu podľa ABC segmentu",
        "chart_intro": "Donut zobrazuje, koľko percent celkového objemu pripadá na segmenty A, B a C.",
        "segment_table": [
            {
                "segment": row.abc_segment,
                "material_count": int(row.unique_material_count),
                "material_share_pct": float(row.material_share_pct),
                "quantity_share_pct": float(row.quantity_share_pct),
            }
            for row in abc_summary.itertuples(index=False)
        ],
        "segment_table_title": "Prehľad ABC segmentov",
        "segment_table_intro": "Tabuľka sumarizuje počty unikátnych materiálov aj podiel objemu v každom ABC segmente.",
        "detail_table": detail_rows,
        "detail_table_title": detail_title,
        "detail_table_headers": detail_headers,
        "detail_table_intro": detail_intro,
        "result_text": (
            f"Najväčší objem nesie materiál {top_material.display_label} ({top_material.material_number}) s objemom "
            f"{top_material.total_quantity:,.1f}. Top 10 materiálov spolu tvorí {top10_share_pct:.1f} % celkového objemu."
        ),
        "interpretation": (
            "ABC segmentácia ukazuje koncentráciu objemu na malej skupine materiálov. "
            "To je bližšie Tableau logike, pretože priamo sleduje MAT_NR na úrovni materiálu."
        ),
        "recommendations": [
            "Segment A sledovať prioritne, lebo rozhoduje o väčšine objemu materiálu.",
            "Top materiály podľa objemu použiť ako základ pre ďalšiu kontrolu spotreby alebo zásobovania.",
            (
                "Ak bude dostupný lookup s minimom skladu, deficitné materiály riešiť prednostne."
                if not comparison_chart.empty
                else "Porovnanie s minimom skladu ostáva vypnuté, kým nebude dostupný lookup RegCis_ciselnik.xlsx."
            ),
        ],
    }


def build_dashboard_data(
    jazdy: pd.DataFrame,
    material: pd.DataFrame,
    *,
    material_views: dict[str, object] | None = None,
) -> dict:
    jazdy["trip_date"] = pd.to_datetime(jazdy["trip_date"])
    material["movement_date"] = pd.to_datetime(material["movement_date"])
    if material_views is None:
        material_views = build_material_views(material)

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
    signed_total_quantity_raw = float(material["quantity_signed"].sum())
    abs_total_quantity_raw = float(material["quantity_abs"].sum())
    material_validation = material_views["validation"]
    signed_total_quantity = round(signed_total_quantity_raw, 1)
    abs_total_quantity = round(abs_total_quantity_raw, 1)
    abs_minus_signed_difference = material_validation["abs_minus_signed_difference"]
    total_material_quantity = signed_total_quantity_raw
    material_monthly = material_views["material_monthly"]
    abc_summary = material_views["abc_summary"]
    top_materials = material_views["top_materials"]
    material_totals = material_views["material_totals"]
    abc_count_chart = build_material_abc_count_chart(material_totals)
    comparison_chart = material_views["comparison_chart"]
    lookup_info = material_views["lookup"]

    advanced_ride_analytics = compute_advanced_ride_analytics(jazdy, trips_per_vehicle)
    advanced_material_analytics = compute_advanced_material_analytics(material_views)

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
    top_material_by_quantity = top_materials.iloc[0]
    top_quantity_month = material_monthly.loc[
        material_monthly["year_month"] == material_views["monthly_summary"]["top_quantity_month"]
    ].iloc[0]

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
                    "Priestorove polia sa hodia len na kontrolu validity startu a hruby odhad presunu, nie na obhajitelnu analyzu presnych tras.",
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
                    "Smer pohybu je odvodeny len zo znamienka mnozstva, nie z explicitneho typoveho pola. Jednotka mnozstva ani cena materialu v datasete nie su.",
                    "Bez lookupu nie je v datasete nazov materialu ani minimalny sklad, preto HTML fallbackuje na MAT_NR.",
                ],
                "answerable": [
                    "unikatne materialy a objem pohybov po mesiacoch",
                    "ABC segmentaciu a top materialy podla objemu",
                    "identifikaciu nulovych mnozstiev a volitelne porovnanie s minimom skladu",
                ],
                "not_answerable": [
                    "presny stav skladu v case",
                    "explicitny typ prijmu vs. vydaja, cena a skladova lokacia",
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
            "raw_records": [
                {
                    "year_month": row.year_month,
                    "weekday_num": int(row.weekday_num),
                    "weekday_sk": row.weekday_sk,
                    "vehicle_id": row.vehicle_id,
                    "ew_start_raw": json_number_or_none(row.ew_start_raw),
                    "el_start_raw": json_number_or_none(row.el_start_raw),
                    "ride_category_tableau": row.ride_category_tableau,
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
                "Celkove mnozstvo": round(total_material_quantity, 0),
                "Priemerne mnozstvo": round(float(material["quantity_signed"].mean()), 1),
                "Median mnozstva": round(float(material["quantity_signed"].median()), 1),
            },
            "totals": {
                "zero_quantity_record_count": int(material_validation["zero_row_count"]),
                "signed_total_quantity": round(signed_total_quantity, 1),
                "netto_signed_effect": round(signed_total_quantity, 1),
                "abs_total_quantity": round(abs_total_quantity, 1),
                "positive_total_quantity": round(float(material_validation["positive_total_quantity"]), 1),
                "negative_total_quantity_abs": round(float(material_validation["negative_total_quantity_abs"]), 1),
                "negative_row_count": int(material_validation["negative_row_count"]),
                "parse_nan_count": int(material_validation["parse_nan_count"]),
                "abs_minus_signed_difference": round(abs_minus_signed_difference, 1),
                "top_quantity_month": month_label(top_quantity_month.year_month),
                "top_quantity_month_value": round(float(top_quantity_month.total_quantity), 1),
            },
            "validation": material_validation,
            "lookup": lookup_info,
            "comparison_chart_generated": bool(material_views["comparison_chart_generated"]),
            "charts": {
                "unikatne_materialy_podla_mesiaca": [
                    {
                        "label": material_month_label_compact(row.year_month),
                        "tooltipLabel": material_month_label_full(row.year_month),
                        "value": int(row.unique_material_count),
                    }
                    for row in material_monthly.itertuples(index=False)
                ],
                "mnozstvo_podla_mesiaca": [
                    {
                        "label": material_month_label_compact(row.year_month),
                        "tooltipLabel": material_month_label_full(row.year_month),
                        "value": round(float(row.total_quantity), 1),
                    }
                    for row in material_monthly.itertuples(index=False)
                ],
                "top_materialy_podla_objemu": [
                    {
                        "label": row.display_label,
                        "value": round(float(row.total_quantity), 1),
                    }
                    for row in top_materials.itertuples(index=False)
                ],
                "abc_segmenty": [
                    {"label": item["label"], "value": item["value"]}
                    for item in abc_count_chart
                ],
                "porovnanie_priemerneho_mnozstva_a_minima_skladu": [
                    {
                        "label": row.display_label,
                        "value": round(float(row.difference), 1),
                    }
                    for row in comparison_chart.itertuples(index=False)
                ],
            },
            "top_material_table": [
                {
                    "label": row.display_label,
                    "material_number": row.material_number,
                    "abc_segment": row.abc_segment,
                    "total_quantity": round(float(row.total_quantity), 1),
                    "quantity_share_pct": round(float(row.quantity_share_pct), 1),
                    "average_quantity": round(float(row.average_quantity), 1),
                }
                for row in top_materials.itertuples(index=False)
            ],
            "comment": (
                f"Tableau-parity objem pohybov = {signed_total_quantity:,.1f} ako SUM(INT(MNOZSTVO)); "
                f"unikatne materialy po mesiacoch sa pocitaju ako DISTINCTCOUNT(MAT_NR). "
                f"Najvacsi objem ma material {top_material_by_quantity.display_label} "
                f"({top_material_by_quantity.material_number}) s objemom {top_material_by_quantity.total_quantity:,.1f}. "
                f"Najsilnejsi mesiac podla objemu pohybov je {month_label(top_quantity_month.year_month)}. "
                f"Lookup minima skladu bol {'najdeny' if lookup_info['found'] else 'nenajdeny'}."
            ),
        },
        "pokrocilejsia_analytika": {
            "jazdy": advanced_ride_analytics,
            "material": advanced_material_analytics,
        },
        "porovnanie_html_vs_tableau": {
            "message": (
                "RIDES sekcia v HTML je zosuladena s Tableau na urovni COUNT/COUNTD KPI, 6 kategorii jazd a logiky "
                "filtra Zobrazit iba validne jazdy. Material sekcia je zosuladena na DISTINCTCOUNT(MAT_NR) po mesiacoch, "
                "SUM(parsed_quantity) a ABC segmentaciu podla kumulativneho podielu objemu."
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
        elif value_format == "float1":
            value_text = fmt_decimal(float(value), 1)
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
                "sub": "DISTINCTCOUNT(MAT_NR)",
                "color": "var(--accent1)",
            },
            {
                "label": "Celkove mnozstvo",
                "value": fmt_compact(material["kpi"]["Celkove mnozstvo"], 1),
                "sub": "SUM(parsed_quantity)",
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

    stock_minimum_card = ""
    if material["comparison_chart_generated"]:
        stock_minimum_card = """
      <div class="card canvas-card">
        <div class="card-title">Porovnanie priemerneho množstva a minima skladu</div>
        <canvas id="chartMaterialMinStockComparison" height="260"></canvas>
      </div>
        """

    material_section = f"""
    <section id="tab-material" class="section">
      <div class="section-title">Pohyby materialu</div>
      <p class="section-copy">{escape(material["comment"])}</p>

      <div class="kpi-row">{material_kpis}</div>

        <div class="grid-2">
        <div class="card canvas-card">
          <div class="card-title">Unikátne materiály podľa mesiaca</div>
          <canvas id="chartMaterialUnique" height="220"></canvas>
        </div>
        <div class="card canvas-card">
          <div class="card-title">Objem pohybov podľa mesiaca</div>
          <canvas id="chartMaterialQty" height="220"></canvas>
        </div>
      </div>

      <div class="grid-2">
        <div class="card canvas-card">
          <div class="card-title">ABC segmenty podľa počtu materiálov</div>
          <div class="donut-panel">
            <div class="donut-canvas-wrap">
              <canvas id="chartAbcSegments" height="260"></canvas>
            </div>
            <div id="chartAbcSegmentsLegend" class="donut-legend" aria-label="Legenda ABC segmentov"></div>
          </div>
        </div>
        <div class="card canvas-card">
          <div class="card-title">Top materiály podľa objemu</div>
          <canvas id="chartTopMaterials" height="260"></canvas>
        </div>
      </div>

      {stock_minimum_card}

      <div class="insight">
        <strong>Rychla interpretacia:</strong>
        Unikatne materialy po mesiacoch sleduju DISTINCTCOUNT(MAT_NR), zatial co objem pohybov ostava SUM(parsed_quantity).
        ABC a top materialy su preto pocitane priamo na urovni MAT_NR, nie cez odvodene skupiny.
      </div>
    </section>
    """

    ride_summary_cards = render_analysis_summary_cards(advanced["jazdy"]["summary_cards"])
    ride_method_list = render_analysis_list(advanced["jazdy"]["method_points"])
    ride_key_findings_list = render_analysis_list(
        advanced["jazdy"]["key_findings"], "analysis-list analysis-list-compact"
    )
    ride_category_rows = [
        [
            item["category"],
            fmt_int(item["trip_count"]),
            fmt_pct(item["share_pct"], 1),
            item["interpretation"],
        ]
        for item in advanced["jazdy"]["category_table"]
    ]
    ride_vehicle_review_rows = [
        [
            item["vehicle_id"],
            fmt_int(item["trip_count"]),
            fmt_int(item["motor_running_stationary_count"]),
            fmt_int(item["movement_without_motohours_count"]),
            fmt_int(item["gps_ping_count"]),
            fmt_pct(item["anomalous_share_pct"], 1),
            fmt_decimal(item["motor_running_stationary_motohours"], 1),
        ]
        for item in advanced["jazdy"]["vehicle_review"]
    ]

    material_summary_cards = render_analysis_summary_cards(advanced["material"]["summary_cards"])
    material_method_list = render_analysis_list(advanced["material"]["method_points"])
    material_recommendation_list = render_analysis_list(
        advanced["material"]["recommendations"], "analysis-list analysis-list-compact"
    )
    material_segment_rows = [
        [
            item["segment"],
            fmt_int(item["material_count"]),
            fmt_pct(item["material_share_pct"], 1),
            fmt_pct(item["quantity_share_pct"], 1),
        ]
        for item in advanced["material"]["segment_table"]
    ]
    material_detail_rows = []
    for item in advanced["material"]["detail_table"]:
        if advanced["material"]["detail_table_title"] == "Materiály pod minimom skladu":
            material_detail_rows.append(
                [
                    item["label"],
                    item["material_number"],
                    fmt_decimal(item["minimum_stock"], 1),
                    fmt_decimal(item["average_quantity"], 1),
                    fmt_decimal(item["difference"], 1),
                    item["abc_segment"],
                ]
            )
        else:
            material_detail_rows.append(
                [
                    item["label"],
                    item["material_number"],
                    item["abc_segment"],
                    fmt_compact(item["total_quantity"], 1),
                    fmt_pct(item["quantity_share_pct"], 1),
                    fmt_decimal(item["average_quantity"], 1),
                ]
            )

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
          <div class="card-title">{escape(advanced["jazdy"]["title"])}</div>
          <div class="analysis-label">Analytická otázka</div>
          <p class="analysis-question">{escape(advanced["jazdy"]["question"])}</p>
        </div>

        <div class="analysis-grid">
          <div class="analysis-block">
            <div class="analysis-block-title">Metodika</div>
            <div class="analysis-method-title">{escape(advanced["jazdy"]["method_title"])}</div>
            <p class="analysis-body">{escape(advanced["jazdy"]["method_intro"])}</p>
            {ride_method_list}
          </div>
          <div class="analysis-block">
            <div class="analysis-block-title">Sumár KPI</div>
            <p class="analysis-body">
              KPI nižšie vychádzajú z plnej populácie jázd a používajú iba 4-kategóriový rámec anomálií
              medzi motohodinami a vzdialenosťou.
            </p>
            <div class="analysis-summary-grid">{ride_summary_cards}</div>
          </div>
        </div>

        <div class="analysis-grid">
          <div class="card canvas-card">
            <div class="card-title">Rozdelenie jázd podľa kategórie anomálie</div>
            <p class="table-intro">
              Donut zobrazuje všetky 4 kategórie. Legenda ukazuje počet jázd aj ich podiel na celej analyzovanej populácii.
            </p>
            <div class="donut-panel">
              <div class="donut-canvas-wrap">
                <canvas id="chartRideAnomalyCategories" height="260"></canvas>
              </div>
              <div id="chartRideAnomalyLegend" class="donut-legend" aria-label="Legenda kategórií anomálií jázd"></div>
            </div>
          </div>
          {render_table(
              "Detail kategórií anomálií",
              [
                  "Kategória",
                  "Počet jázd",
                  "Podiel",
                  "Interpretácia",
              ],
              ride_category_rows,
              intro=advanced["jazdy"]["category_table_intro"],
          )}
        </div>

        <div class="analysis-callout">
          <div class="analysis-block-title">Kľúčové zistenia</div>
          {ride_key_findings_list}
        </div>

        {render_table(
            "Vozidlový review anomálií",
            [
                "Vozidlo",
                "Jazdy spolu",
                "Motor beží, auto stojí",
                "Pohyb bez motohodín",
                "Nulová jazda (GPS ping)",
                "Podiel anomálií",
                "Motohodiny pri státí",
            ],
            ride_vehicle_review_rows,
            intro=advanced["jazdy"]["vehicle_review_intro"],
        )}
      </div>

      <div class="analysis-report">
        <div class="analysis-head">
          <div class="analysis-kicker">Dataset 2 | Pohyby materiálu</div>
          <div class="card-title">Pokročilá úloha: ABC koncentrácia objemu a kontrola top materiálov</div>
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
            <div class="card-title">{escape(advanced["material"]["chart_title"])}</div>
            <p class="table-intro">{escape(advanced["material"]["chart_intro"])}</p>
            <canvas id="chartMaterialSegmentsAdvanced" height="250"></canvas>
          </div>
          {render_table(
              advanced["material"]["segment_table_title"],
              [
                  "Segment",
                  "Materiály",
                  "Podiel materiálov",
                  "Podiel množstva",
              ],
              material_segment_rows,
              intro=advanced["material"]["segment_table_intro"],
          )}
        </div>

        {render_table(
            advanced["material"]["detail_table_title"],
            advanced["material"]["detail_table_headers"],
            material_detail_rows,
            intro=advanced["material"]["detail_table_intro"],
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
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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

    .recom-list {
      margin: 0;
      padding-left: 18px;
      color: var(--text-soft);
      font-size: 13px;
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

    function roundedRectPath(ctx, x, y, width, height, radius) {
      const r = Math.min(radius, width / 2, height / 2);
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + width, y, x + width, y + height, r);
      ctx.arcTo(x + width, y + height, x, y + height, r);
      ctx.arcTo(x, y + height, x, y, r);
      ctx.arcTo(x, y, x + width, y, r);
      ctx.closePath();
    }

    function fillRoundedRect(ctx, x, y, width, height, radius) {
      roundedRectPath(ctx, x, y, width, height, radius);
      ctx.fill();
    }

    function getVisibleLabelStep(itemCount, maxVisibleLabels = 14) {
      return Math.max(1, Math.ceil(itemCount / Math.max(1, maxVisibleLabels)));
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
        const pctText = state.percentFormatter(value / state.total);
        const color = state.colors[index % state.colors.length];
        const legendValue = state.legendValueFormatter(item, value, pctText);

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

        const pctText = state.percentFormatter(value / state.total);
        state.geometry.push({
          startAngle,
          endAngle,
          label: item.label,
          tooltipValue: state.tooltipValueFormatter(item, value, pctText),
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
      ctx.fillText(state.centerLabel, state.centerX, state.centerY - 4);
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
      const percentDigits = options.percentDigits ?? 1;
      state.centerLabel = options.centerLabel || "TOTAL";
      state.ariaLabel = options.ariaLabel
        || "Interaktívny donut graf. Fokusuj legendu pre zvýraznenie zodpovedajúceho segmentu.";
      state.percentFormatter = options.percentFormatter
        || ((ratio) => formatNumber(ratio * 100, percentDigits) + "%");
      state.legendValueFormatter = options.legendValueFormatter
        || ((item, value, pctText) => `${state.formatter(value)} | ${pctText}`);
      state.tooltipValueFormatter = options.tooltipValueFormatter || state.legendValueFormatter;

      if (canvas.__interactiveDonutState?.rafId) {
        window.cancelAnimationFrame(canvas.__interactiveDonutState.rafId);
      }

      canvas.__interactiveDonutState = state;
      canvas.setAttribute("role", "img");
      canvas.setAttribute("aria-label", state.ariaLabel);

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

      const state = {
        ...setup,
        items,
        color,
        formatter,
        options,
        activeIndex: null,
        hitBoxes: [],
      };

      function render() {
        const { ctx, width, height } = state;
        const pad = { top: 20, right: 14, bottom: 40, left: 54 };
        const chartWidth = width - pad.left - pad.right;
        const chartHeight = height - pad.top - pad.bottom;
        const maxValue = Math.max(...items.map((item) => Number(item.value))) * 1.12 || 1;
        const step = chartWidth / items.length;
        const barWidth = Math.max(10, Math.min(28, step * 0.62));
        const labelStep = getVisibleLabelStep(items.length, options.maxVisibleLabels || 14);
        const hitBoxes = [];

        ctx.clearRect(0, 0, width, height);
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
          const baseBarHeight = (value / maxValue) * chartHeight;
          const x = pad.left + index * step + (step - barWidth) / 2;
          const lift = state.activeIndex === index ? 4 : 0;
          const y = pad.top + chartHeight - baseBarHeight - lift;
          const visibleHeight = Math.max(baseBarHeight + lift, 2);
          const hasActive = state.activeIndex !== null;
          const isActive = state.activeIndex === index;

          ctx.save();
          if (hasActive && !isActive) {
            ctx.globalAlpha = 0.44;
          }

          const gradient = ctx.createLinearGradient(0, y, 0, y + visibleHeight);
          gradient.addColorStop(0, isActive ? color : color + "dd");
          gradient.addColorStop(1, isActive ? color + "66" : color + "33");
          ctx.fillStyle = gradient;

          if (isActive) {
            ctx.shadowColor = color + "52";
            ctx.shadowBlur = 22;
            ctx.shadowOffsetY = 6;
          }

          fillRoundedRect(ctx, x, y, barWidth, visibleHeight, 5);
          ctx.restore();

          if (isActive) {
            ctx.save();
            ctx.strokeStyle = "rgba(235, 241, 251, 0.2)";
            ctx.lineWidth = 1;
            roundedRectPath(ctx, x, y, barWidth, visibleHeight, 5);
            ctx.stroke();
            ctx.restore();
          }

          if (options.tooltip) {
            const tooltipFormatter = options.tooltipFormatter || formatter;
            hitBoxes.push({
              x: x - 2,
              y,
              width: barWidth + 4,
              height: visibleHeight + 4,
              label: item.tooltipLabel || item.label,
              tooltipValue: tooltipFormatter(value, item),
            });
          }

          if (index % labelStep === 0) {
            ctx.fillStyle = palette.textSoft;
            ctx.font = "10px DM Mono";
            ctx.textAlign = "center";
            ctx.fillText(item.label, x + barWidth / 2, height - 14);
          }
        });

        state.hitBoxes = hitBoxes;
      }

      state.render = render;
      const canvas = state.canvas;
      canvas.__barChartState = state;
      state.render();

      if (!options.tooltip) {
        canvas.style.cursor = "default";
        return;
      }

      if (canvas.dataset.barChartHoverBound === "true") {
        return;
      }

      canvas.dataset.barChartHoverBound = "true";
      canvas.addEventListener("mousemove", (event) => {
        const currentState = canvas.__barChartState;
        if (!currentState) {
          return;
        }

        const rect = canvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        const hitIndex = (currentState.hitBoxes || []).findIndex(
          (item) =>
            x >= item.x
            && x <= item.x + item.width
            && y >= item.y
            && y <= item.y + item.height
        );

        const nextIndex = hitIndex === -1 ? null : hitIndex;
        if (currentState.activeIndex !== nextIndex) {
          currentState.activeIndex = nextIndex;
          currentState.render();
        }

        canvas.style.cursor = nextIndex === null ? "default" : "pointer";
        if (nextIndex === null) {
          hideChartTooltip();
          return;
        }

        showChartTooltip(event, currentState.hitBoxes[nextIndex]);
      });

      canvas.addEventListener("mouseleave", () => {
        const currentState = canvas.__barChartState;
        canvas.style.cursor = "default";
        hideChartTooltip();
        if (currentState && currentState.activeIndex !== null) {
          currentState.activeIndex = null;
          currentState.render();
        }
      });
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

    function buildRideView(showValidOnly) {
      const filteredRides = getFilteredRides(showValidOnly);
      const vehicleBreakdown = computeVehicleBreakdown(filteredRides);
      const metrics = computeRideMetrics(filteredRides, vehicleBreakdown, showValidOnly);
      const charts = computeRideCharts(filteredRides, vehicleBreakdown);

      return {
        showValidOnly,
        filteredRides,
        metrics,
        charts,
        vehicles: vehicleBreakdown,
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

      return `
        ${renderRideTableCard(
          "Vyťaženosť vozidiel",
          ["Vozidlo", "Počet jázd", "Podiel zo všetkých", "Validné jazdy", "Podiel validných", "Dominantná kategória"],
          vehicleRows
        )}
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
          V tomto móde sa KPI, grafy aj tabuľka rátajú z toho istého filtrovaného datasetu jázd.
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
        {
          legendId: "chartTripDistanceLegend",
          ariaLabel: "Kategórie jázd podľa Tableau. Fokusuj legendu pre zvýraznenie zodpovedajúceho segmentu.",
        }
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
      drawBarChart(
        "chartMaterialUnique",
        dashboard.material.charts.unikatne_materialy_podla_mesiaca,
        palette.accent3,
        (value) => formatNumber(value, 0),
        {
          tooltip: true,
          maxVisibleLabels: 12,
          tooltipFormatter: (value) => `Unikátne materiály: ${formatNumber(value, 0)}`,
        }
      );
      drawBarChart(
        "chartMaterialQty",
        dashboard.material.charts.mnozstvo_podla_mesiaca,
        palette.accent4,
        (value) => formatCompact(value),
        {
          tooltip: true,
          maxVisibleLabels: 12,
          tooltipFormatter: (value) => `Celkové množstvo: ${formatNumber(value, 1)}`,
        }
      );
      drawInteractiveDonutChart(
        "chartAbcSegments",
        dashboard.material.charts.abc_segmenty,
        [palette.accent1, palette.accent4, palette.accent3],
        {
          legendId: "chartAbcSegmentsLegend",
          ariaLabel: "ABC segmenty podľa počtu materiálov. Fokusuj legendu pre zvýraznenie zodpovedajúceho segmentu.",
          percentDigits: 1,
          legendValueFormatter: (item, value, pctText) => `${formatNumber(value, 0)} materiálov | ${pctText}`,
          tooltipValueFormatter: (item, value, pctText) => `${formatNumber(value, 0)} materiálov | ${pctText}`,
        }
      );
      drawHorizontalBars(
        "chartTopMaterials",
        dashboard.material.charts.top_materialy_podla_objemu,
        palette.accent3,
        (value) => formatCompact(value),
        {
          tooltip: true,
          tooltipFormatter: (value) => `Celkové množstvo: ${formatNumber(value, 1)}`,
        }
      );
      if (
        dashboard.material.comparison_chart_generated
        && dashboard.material.charts.porovnanie_priemerneho_mnozstva_a_minima_skladu.length
      ) {
        drawHorizontalBars(
          "chartMaterialMinStockComparison",
          dashboard.material.charts.porovnanie_priemerneho_mnozstva_a_minima_skladu,
          palette.accent2,
          (value) => formatNumber(value, 1),
          {
            tooltip: true,
            tooltipFormatter: (value) => `Deficit voči minimu: ${formatNumber(value, 1)}`,
          }
        );
      }
    }

    function drawAdvancedCharts() {
      drawInteractiveDonutChart(
        "chartRideAnomalyCategories",
        dashboard.pokrocilejsia_analytika.jazdy.chart,
        [palette.accent3, palette.accent4, palette.accent2, palette.accent1],
        {
          legendId: "chartRideAnomalyLegend",
          centerLabel: "JAZDY",
          ariaLabel: "Kategórie anomálií medzi motohodinami a vzdialenosťou. Fokusuj legendu pre zvýraznenie zodpovedajúcej kategórie.",
          legendValueFormatter: (item, value, pctText) => `${formatNumber(value, 0)} jázd | ${pctText}`,
          tooltipValueFormatter: (item, value, pctText) => `${formatNumber(value, 0)} jázd | ${pctText}`,
        }
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


def print_build_summary(material_views: dict[str, object], ride_analytics: dict | None = None) -> None:
    kpi_summary = material_views["kpi_summary"]
    material_monthly = material_views["material_monthly"]
    abc_verification = material_views["abc_verification"]
    top_materials = material_views["top_materials"]
    lookup_info = material_views["lookup"]
    comparison_chart_generated = material_views["comparison_chart_generated"]

    print("Build summary:")
    print(f"  rides input path: {JAZDY_INPUT}")
    print(f"  material input path: {MATERIAL_INPUT}")
    print(f"  html output path: {HTML_OUTPUT}")
    print(f"  material row count: {kpi_summary['total_rows']}")
    print(f"  distinct material count: {kpi_summary['unique_materials']}")
    print(f"  total quantity: {kpi_summary['total_quantity']:.1f}")
    print(f"  average quantity: {kpi_summary['average_quantity']:.1f}")
    print(f"  zero quantity rows: {kpi_summary['zero_rows']}")
    print("  first 5 monthly values for Unikátne materiály podľa mesiaca:")
    for row in material_monthly.head(5).itertuples(index=False):
        print(f"    {row.year_month}: {int(row.unique_material_count)}")
    print("  first 5 monthly values for Objem pohybov podľa mesiaca:")
    for row in material_monthly.head(5).itertuples(index=False):
        print(f"    {row.year_month}: {float(row.total_quantity):.1f}")
    print(f"  ABC segment counts: {abc_verification['segment_counts']}")
    print("  top 10 materials by total quantity:")
    for row in top_materials.itertuples(index=False):
        print(f"    {row.material_number} | {row.display_label} | {float(row.total_quantity):.1f}")
    print(f"  RegCis_ciselnik.xlsx found: {lookup_info['found']}")
    print(
        "  stock-minimum comparison chart: "
        + ("generated" if comparison_chart_generated else "skipped")
    )
    if ride_analytics is not None:
        validation = ride_analytics["validation"]
        category_counts = validation["category_counts"]
        print("  ride anomaly validation:")
        print(
            f"    analyzed rides={validation['analyzed_ride_count']}"
            f" | category total={validation['category_total_count']}"
            f" | share sum={validation['category_share_pct_sum']:.1f}%"
        )
        print(
            "    categories: "
            f"Normálna jazda={category_counts['Normálna jazda']}, "
            f"Pohyb bez motohodín={category_counts['Pohyb bez motohodín']}, "
            f"Motor beží, auto stojí={category_counts['Motor beží, auto stojí']}, "
            f"Nulová jazda (GPS ping)={category_counts['Nulová jazda (GPS ping)']}"
        )
        print(
            f"    anomalous rides={validation['anomaly_ride_count']} "
            f"({validation['anomaly_share_pct']:.1f}%)"
            f" | motor-running idle hours={validation['motor_running_stationary_motohours']:.1f}"
        )
        print(
            f"    thresholds: distance<{validation['distance_threshold_m']:.0f}m"
            f" | zero epsilon={validation['zero_epsilon']}"
        )


def main() -> None:
    VIS_DIR.mkdir(parents=True, exist_ok=True)

    jazdy = load_jazdy_dataset(JAZDY_INPUT)
    material = load_material_dataset(MATERIAL_INPUT)
    material_views = build_material_views(material)

    dashboard = build_dashboard_data(jazdy, material, material_views=material_views)

    html = build_html(dashboard)
    HTML_OUTPUT.write_text(html, encoding="utf-8")

    print_build_summary(material_views, dashboard["pokrocilejsia_analytika"]["jazdy"])


if __name__ == "__main__":
    main()
