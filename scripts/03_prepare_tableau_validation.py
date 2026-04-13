from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs"

JAZDY_INPUT = OUT_DIR / "cleaned_jazdy.csv"
MATERIAL_INPUT = OUT_DIR / "cleaned_material.csv"
VALIDATION_OUTPUT = OUT_DIR / "tableau_validation_metrics.csv"


def build_metrics(jazdy: pd.DataFrame, material: pd.DataFrame) -> pd.DataFrame:
    valid_jazdy = jazdy.loc[~jazdy["near_zero_trip"]]

    def format_value(value: float | int) -> str:
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.2f}".rstrip("0").rstrip(".")

    metrics = [
        {
            "dataset": "jazdy",
            "metric_name": "celkovy_pocet_zaznamov",
            "python_value": format_value(len(jazdy)),
            "comment": "COUNT riadkov v cleaned_jazdy.csv",
        },
        {
            "dataset": "jazdy",
            "metric_name": "pocet_vozidiel",
            "python_value": format_value(jazdy["vehicle_id"].nunique()),
            "comment": "COUNTD(vehicle_id)",
        },
        {
            "dataset": "jazdy",
            "metric_name": "platne_jazdy_over_50m",
            "python_value": format_value(len(valid_jazdy)),
            "comment": "COUNT riadkov kde near_zero_trip = False",
        },
        {
            "dataset": "jazdy",
            "metric_name": "near_zero_zaznamy",
            "python_value": format_value(int(jazdy["near_zero_trip"].sum())),
            "comment": "COUNT riadkov kde near_zero_trip = True",
        },
        {
            "dataset": "jazdy",
            "metric_name": "priemer_km_na_platnu_jazdu",
            "python_value": format_value(round(valid_jazdy["distance_km"].mean(), 2)),
            "comment": "AVG(distance_km) kde near_zero_trip = False",
        },
        {
            "dataset": "jazdy",
            "metric_name": "potencialne_neefektivne_zaznamy",
            "python_value": format_value(int(jazdy["potentially_inefficient_trip"].sum())),
            "comment": "COUNT riadkov kde potentially_inefficient_trip = True",
        },
        {
            "dataset": "material",
            "metric_name": "celkovy_pocet_pohybov",
            "python_value": format_value(len(material)),
            "comment": "COUNT riadkov v cleaned_material.csv",
        },
        {
            "dataset": "material",
            "metric_name": "pocet_materialov",
            "python_value": format_value(material["material_number"].nunique()),
            "comment": "COUNTD(material_number)",
        },
        {
            "dataset": "material",
            "metric_name": "celkove_mnozstvo",
            "python_value": format_value(round(material["quantity_clean"].sum(), 1)),
            "comment": "SUM(quantity_clean)",
        },
        {
            "dataset": "material",
            "metric_name": "priemerne_mnozstvo",
            "python_value": format_value(round(material["quantity_clean"].mean(), 1)),
            "comment": "AVG(quantity_clean)",
        },
        {
            "dataset": "material",
            "metric_name": "median_mnozstva",
            "python_value": format_value(round(material["quantity_clean"].median(), 1)),
            "comment": "MEDIAN(quantity_clean)",
        },
        {
            "dataset": "material",
            "metric_name": "abc_segment_a_materialy",
            "python_value": format_value(material.loc[material["abc_segment"] == "A", "material_number"].nunique()),
            "comment": "COUNTD(material_number) kde abc_segment = 'A'",
        },
    ]

    return pd.DataFrame(metrics)


def main() -> None:
    jazdy = pd.read_csv(JAZDY_INPUT)
    material = pd.read_csv(MATERIAL_INPUT)

    metrics = build_metrics(jazdy, material)
    metrics.to_csv(VALIDATION_OUTPUT, index=False)

    print(f"Prepared validation file: {VALIDATION_OUTPUT}")
    print(metrics.to_string(index=False))


if __name__ == "__main__":
    main()
