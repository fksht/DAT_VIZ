from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs"
VIS_DIR = ROOT / "visualization"

JAZDY_INPUT = OUT_DIR / "cleaned_jazdy.csv"
MATERIAL_INPUT = OUT_DIR / "cleaned_material.csv"
JSON_OUTPUT = OUT_DIR / "dashboard_data.json"
HTML_OUTPUT = VIS_DIR / "analyza_dashboard.html"


def fmt_int(value: float | int) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def fmt_decimal(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def month_label(value: str) -> str:
    year, month = value.split("-")
    return f"{month}/{year}"


def build_dashboard_data(jazdy: pd.DataFrame, material: pd.DataFrame) -> dict:
    jazdy["trip_date"] = pd.to_datetime(jazdy["trip_date"])
    material["movement_date"] = pd.to_datetime(material["movement_date"])

    valid_jazdy = jazdy.loc[~jazdy["near_zero_trip"]].copy()
    trips_per_vehicle = (
        jazdy.groupby("vehicle_id", as_index=False)
        .agg(
            trip_count=("vehicle_id", "size"),
            valid_trip_count=("near_zero_trip", lambda series: int((~series).sum())),
            inefficient_trip_count=("potentially_inefficient_trip", "sum"),
        )
        .sort_values(["trip_count", "vehicle_id"], ascending=[False, True])
    )
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
        .agg(unique_material_count=("material_number", "nunique"))
        .sort_values("abc_segment")
    )

    most_used_vehicle = trips_per_vehicle.iloc[0]
    least_used_vehicle = trips_per_vehicle.iloc[-1]
    most_active_weekday = rides_weekday.sort_values("trip_count", ascending=False).iloc[0]
    top_prefix = prefix_summary.iloc[0]

    dashboard = {
        "meta": {
            "generated_from": "outputs/dashboard_data.json",
            "html_role": "Doplnkovy HTML vystup. Finalna validacia patri do Tableau.",
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
            "comment": (
                f"Najviac jazd malo vozidlo {most_used_vehicle.vehicle_id} ({int(most_used_vehicle.trip_count)}), "
                f"najmenej {least_used_vehicle.vehicle_id} ({int(least_used_vehicle.trip_count)}). "
                f"Najsilnejsi den je {most_active_weekday.weekday_sk}. "
                f"Near-zero zaznamy tvoria {jazdy['near_zero_trip'].mean() * 100:.1f} % vsetkych zaznamov, "
                "preto sa oplati pri Tableau dashboarde mat filter na tieto zaznamy."
            ),
        },
        "material": {
            "kpi": {
                "Celkovy pocet pohybov": int(len(material)),
                "Pocet materialov": int(material["material_number"].nunique()),
                "Pocet prefixov": int(material["material_prefix"].nunique()),
                "Celkove mnozstvo": round(material["quantity_clean"].sum(), 0),
                "Priemerne mnozstvo": round(material["quantity_clean"].mean(), 1),
                "Median mnozstva": round(material["quantity_clean"].median(), 1),
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
            "comment": (
                f"Najaktivnejsi prefix podla poctu pohybov je {top_prefix.material_prefix} "
                f"({int(top_prefix.movement_count)} pohybov). "
                "Interpretacia je o pohyboch materialu, nie o presnom stave skladu, "
                "preto sa v texte ani vo vizualizaciach nehovori o zasobach na sklade."
            ),
        },
        "pokrocilejsia_analytika": {
            "jazdy": {
                "potentially_inefficient_trip_count": int(jazdy["potentially_inefficient_trip"].sum()),
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
            },
            "material": {
                "abc_summary": [
                    {
                        "abc_segment": row.abc_segment,
                        "unique_material_count": int(row.unique_material_count),
                    }
                    for row in abc_summary.itertuples(index=False)
                ],
                "description": (
                    "Pouzita je jednoducha ABC segmentacia podla kumulativneho podielu na celkovom mnozstve. "
                    "Je interpretovatelnejsia ako clustering a lepsie sa obhajuje v studentskom projekte."
                ),
            },
        },
        "porovnanie_html_vs_tableau": {
            "message": (
                "HTML je doplnkovy artefakt postaveny na tych istych CSV. Ak sa cisla v HTML a Tableau lisia, "
                "najprv treba skontrolovat filtre, typy datumov a rozdiel medzi COUNT a COUNTD. "
                "Pri finalnej obhajobe ma prednost validacia v Tableau."
            )
        },
    }

    return dashboard


def render_kpis(items: dict) -> str:
    cards = []
    for label, value in items.items():
        if isinstance(value, float) and value.is_integer():
            formatted = fmt_int(value)
        elif isinstance(value, float):
            formatted = fmt_decimal(value, 1 if value == round(value, 1) else 2)
        else:
            formatted = fmt_int(value)
        cards.append(
            f"""
            <div class="kpi-card">
              <div class="kpi-label">{escape(label)}</div>
              <div class="kpi-value">{escape(formatted)}</div>
            </div>
            """
        )
    return "\n".join(cards)


def render_bar_chart(title: str, items: list[dict], value_kind: str = "int") -> str:
    max_value = max((item["value"] for item in items), default=1) or 1
    rows = []
    for item in items:
        label = escape(str(item["label"]))
        value = item["value"]
        width = value / max_value * 100
        if value_kind == "float":
            value_text = fmt_decimal(float(value), 1)
        else:
            value_text = fmt_int(float(value))
        rows.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">{label}</div>
              <div class="bar-track"><div class="bar-fill" style="width: {width:.2f}%"></div></div>
              <div class="bar-value">{escape(value_text)}</div>
            </div>
            """
        )
    return f"""
    <div class="card">
      <h3>{escape(title)}</h3>
      <div class="bar-chart">
        {''.join(rows)}
      </div>
    </div>
    """


def render_table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    row_html = []
    for row in rows:
        row_html.append("<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>")
    return f"""
    <h3>{escape(title)}</h3>
    <table>
      <thead><tr>{header_html}</tr></thead>
      <tbody>{''.join(row_html)}</tbody>
    </table>
    """


def build_html(dashboard: dict) -> str:
    jazdy = dashboard["jazdy"]
    material = dashboard["material"]
    advanced = dashboard["pokrocilejsia_analytika"]
    understanding = dashboard["pochopenie_dat"]

    top_vehicle_rows = []
    for item in advanced["jazdy"]["top_vehicle_shares"]:
        top_vehicle_rows.append(
            [
                item["vehicle_id"],
                fmt_int(item["trip_count"]),
                fmt_int(item["inefficient_trip_count"]),
                fmt_decimal(item["inefficient_share_pct"], 1) + " %",
            ]
        )

    abc_rows = []
    for item in advanced["material"]["abc_summary"]:
        abc_rows.append(
            [
                item["abc_segment"],
                fmt_int(item["unique_material_count"]),
            ]
        )

    json_blob = json.dumps(dashboard, ensure_ascii=False, indent=2)

    return f"""<!DOCTYPE html>
<html lang="sk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Analyza datasetov - HTML prehlad</title>
  <style>
    :root {{
      --bg: #f6f7f4;
      --card: #ffffff;
      --line: #d8ddd2;
      --text: #1f2a1f;
      --muted: #5c6758;
      --accent: #315c3a;
      --accent-soft: #dfeadf;
      --warn: #8b5e34;
      --warn-soft: #f4eadf;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    header {{
      padding: 32px 20px 24px;
      background: #eef3ea;
      border-bottom: 1px solid var(--line);
    }}
    header h1 {{
      margin: 0 0 8px;
      font-size: 30px;
    }}
    header p {{
      margin: 0;
      max-width: 900px;
      color: var(--muted);
    }}
    nav {{
      padding: 12px 20px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfa;
    }}
    nav a {{
      color: var(--accent);
      text-decoration: none;
      margin-right: 16px;
      font-weight: 600;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 20px;
    }}
    section {{
      margin-bottom: 28px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 24px;
    }}
    h3 {{
      margin: 0 0 14px;
      font-size: 18px;
    }}
    .section-note {{
      margin: 0 0 16px;
      color: var(--muted);
    }}
    .grid-2 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 16px;
    }}
    .grid-4 {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 18px;
      box-shadow: 0 1px 1px rgba(0, 0, 0, 0.03);
    }}
    .kpi-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px 16px;
    }}
    .kpi-label {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .kpi-value {{
      font-size: 28px;
      font-weight: 700;
      color: var(--accent);
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
    }}
    li + li {{
      margin-top: 6px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 120px 1fr 92px;
      gap: 10px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .bar-label, .bar-value {{
      font-size: 13px;
    }}
    .bar-track {{
      background: #edf1ea;
      border-radius: 999px;
      height: 14px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 999px;
      background: var(--accent);
    }}
    .callout {{
      padding: 14px 16px;
      border-radius: 10px;
      background: var(--accent-soft);
      border: 1px solid var(--line);
    }}
    .callout.warn {{
      background: var(--warn-soft);
      color: #593712;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
    }}
    .meta {{
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
    }}
    code {{
      background: #eef1ec;
      padding: 1px 5px;
      border-radius: 4px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Analyza datasetov - doplnkovy HTML prehlad</h1>
    <p>
      Tento vystup je doplnok k povinnej Tableau casti. Zobrazuje iba metriky, ktore boli vygenerovane z aktualnych CSV
      vystupov. Zaverecna validacia patri do Tableau.
    </p>
  </header>

  <nav>
    <a href="#pochopenie">Pochopenie dat</a>
    <a href="#jazdy">Jazdy vozidiel</a>
    <a href="#material">Zasobovanie materialmi</a>
    <a href="#pokrocilejsia">Pokrocilejsia analytika</a>
    <a href="#porovnanie">Porovnanie HTML vs Tableau</a>
  </nav>

  <main>
    <section id="pochopenie">
      <h2>Pochopenie dat</h2>
      <p class="section-note">
        Najprv treba presne povedat, co datasety obsahuju a co uz z nich bez dalsieho kontextu zistit nevieme.
      </p>
      <div class="grid-2">
        <div class="card">
          <h3>Dataset jazdy</h3>
          <p>
            Povodny Excel ma {fmt_int(understanding["jazdy"]["record_count"])} riadkov a 14 povodnych poli.
            Obdobie: {escape(understanding["jazdy"]["date_range"][0])} az {escape(understanding["jazdy"]["date_range"][1])}.
          </p>
          <ul>
            <li>Zakladne polia: datum, vozidlo, cas od/do, start a koniec polohy, doba statia, motohodiny, vzdialenost medzi startom a koncom.</li>
            <li>Pre analyzu sa pouziva najma datum, vozidlo, trvanie jazdy, priama vzdialenost, flag near-zero a heuristicky flag potencialne neefektivneho zaznamu.</li>
          </ul>
          <div class="meta">Limity:</div>
          <ul>
            {''.join(f'<li>{escape(item)}</li>' for item in understanding["jazdy"]["limitations"])}
          </ul>
        </div>
        <div class="card">
          <h3>Dataset material</h3>
          <p>
            Povodny Excel ma {fmt_int(understanding["material"]["record_count"])} riadkov a 4 povodne polia.
            Obdobie: {escape(understanding["material"]["date_range"][0])} az {escape(understanding["material"]["date_range"][1])}.
          </p>
          <ul>
            <li>Zakladne polia: datum pohybu, rok, cislo materialu a mnozstvo.</li>
            <li>Pre analyzu sa pouziva najma datum, prefix materialu, mnozstvo a ABC segment materialu.</li>
          </ul>
          <div class="meta">Limity:</div>
          <ul>
            {''.join(f'<li>{escape(item)}</li>' for item in understanding["material"]["limitations"])}
          </ul>
        </div>
      </div>
      <div class="grid-2" style="margin-top: 16px;">
        <div class="callout">
          <strong>Co vieme zodpovedat:</strong> vytazenost vozidiel, vyvoj zaznamov v case, podiel near-zero zaznamov,
          top vozidla, top prefixy materialov a ABC segmentaciu materialov.
        </div>
        <div class="callout warn">
          <strong>Co netvrdime:</strong> presne trasy po cestach, financne uspory, stav zasob na sklade, adresy,
          ani dovody jazd. Tieto informacie v datach nie su.
        </div>
      </div>
    </section>

    <section id="jazdy">
      <h2>Jazdy vozidiel</h2>
      <p class="section-note">{escape(jazdy["comment"])}</p>
      <div class="grid-4">
        {render_kpis(jazdy["kpi"])}
      </div>
      <div class="grid-2" style="margin-top: 16px;">
        {render_bar_chart("Pocet zaznamov podla mesiaca", jazdy["charts"]["jazdy_podla_mesiaca"])}
        {render_bar_chart("Pocet zaznamov podla dna v tyzdni", jazdy["charts"]["jazdy_podla_dna"])}
      </div>
      <div class="grid-2" style="margin-top: 16px;">
        {render_bar_chart("Top vozidla podla poctu zaznamov", jazdy["charts"]["top_vozidla_podla_poctu_jazd"])}
        {render_bar_chart("Rozdelenie podla priamej vzdialenosti", jazdy["charts"]["rozdelenie_podla_vzdialenosti"])}
      </div>
    </section>

    <section id="material">
      <h2>Zasobovanie materialmi</h2>
      <p class="section-note">{escape(material["comment"])}</p>
      <div class="grid-4">
        {render_kpis(material["kpi"])}
      </div>
      <div class="grid-2" style="margin-top: 16px;">
        {render_bar_chart("Pohyby materialu podla mesiaca", material["charts"]["pohyby_podla_mesiaca"])}
        {render_bar_chart("Celkove mnozstvo podla mesiaca", material["charts"]["mnozstvo_podla_mesiaca"], value_kind="float")}
      </div>
      <div class="grid-2" style="margin-top: 16px;">
        {render_bar_chart("Top prefixy podla poctu pohybov", material["charts"]["top_prefixy_podla_pohybov"])}
        {render_bar_chart("ABC segmenty podla poctu materialov", material["charts"]["abc_segmenty"])}
      </div>
    </section>

    <section id="pokrocilejsia">
      <h2>Pokrocilejsia analytika</h2>
      <div class="grid-2">
        <div class="card">
          <h3>Jazdy: potencialne neefektivne zaznamy</h3>
          <p>{escape(advanced["jazdy"]["description"])}</p>
          <p>
            Pocet heuristicky oznacenych zaznamov:
            <strong>{fmt_int(advanced["jazdy"]["potentially_inefficient_trip_count"])}</strong>.
          </p>
          {render_table(
              "Vozidla s najvyssim podielom oznacenych zaznamov",
              ["Vozidlo", "Vsetky zaznamy", "Oznacene", "Podiel"],
              top_vehicle_rows,
          )}
        </div>
        <div class="card">
          <h3>Material: ABC segmentacia</h3>
          <p>{escape(advanced["material"]["description"])}</p>
          {render_table(
              "Pocet unikatnych materialov v segmentoch",
              ["ABC segment", "Pocet materialov"],
              abc_rows,
          )}
          <div class="meta">
            Segmentacia je zalozena na kumulativnom podiele na celkovom mnozstve pohybov, nie na cene a nie na skladovej hodnote.
          </div>
        </div>
      </div>
    </section>

    <section id="porovnanie">
      <h2>Kratke porovnanie HTML/AI vs Tableau validation</h2>
      <div class="card">
        <p>{escape(dashboard["porovnanie_html_vs_tableau"]["message"])}</p>
        <ul>
          <li>HTML je len doplnok a vznikol z dat v <code>outputs/dashboard_data.json</code>.</li>
          <li>Tableau je povinna cast zadania a ma sluzit na finalnu kontrolu KPI aj grafov.</li>
          <li>Ak sa vysledky lisia, do spravy patri vysvetlenie rozdielu a odkaz na validaciu v Tableau.</li>
        </ul>
      </div>
    </section>
  </main>

  <script id="dashboard-data" type="application/json">{json_blob}</script>
</body>
</html>
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    VIS_DIR.mkdir(parents=True, exist_ok=True)

    jazdy = pd.read_csv(JAZDY_INPUT)
    material = pd.read_csv(MATERIAL_INPUT)

    dashboard = build_dashboard_data(jazdy, material)

    with JSON_OUTPUT.open("w", encoding="utf-8") as handle:
        json.dump(dashboard, handle, ensure_ascii=False, indent=2)

    html = build_html(dashboard)
    HTML_OUTPUT.write_text(html, encoding="utf-8")

    print("Built dashboard artifacts:")
    print(f"  {JSON_OUTPUT}")
    print(f"  {HTML_OUTPUT}")


if __name__ == "__main__":
    main()
