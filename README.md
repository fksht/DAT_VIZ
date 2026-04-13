# DAT_VIZ

Jednoducha a validovana studentska praca k analyzam dvoch datasetov:

- `dataset_jazdy_2024.xlsx`
- `dataset_material_2023_2025.xlsx`

Projekt je pripraveny tak, aby sa dal lahko spustit, lahko importovat do Tableau a lahko obhajit bez zbytocnych tvrdeni navyse.

## Co je povinne a co je len doplnok

- Povinne: Tableau dashboardy postavene z `outputs/cleaned_jazdy.csv` a `outputs/cleaned_material.csv`
- Doplnok: `visualization/analyza_dashboard.html`

HTML nenahradza Tableau. Sluzí len ako jednoduchy sprievodny vystup.

## Finalne subory, ktore maju zmysel

```text
data/raw/
  dataset_jazdy_2024.xlsx
  dataset_material_2023_2025.xlsx

scripts/
  01_prepare_data.py
  02_build_dashboard.py
  03_prepare_tableau_validation.py

outputs/
  cleaned_jazdy.csv
  cleaned_material.csv
  dashboard_data.json
  tableau_validation_metrics.csv

visualization/
  analyza_dashboard.html

tableau/
  tableau_import_notes_sk.md

report/
  report_notes_sk.md
```

## Ako to spustit

Ak uz mate pripravene virtualne prostredie:

```bash
source .venv/bin/activate
python scripts/01_prepare_data.py
python scripts/02_build_dashboard.py
python scripts/03_prepare_tableau_validation.py
```

Ak virtualne prostredie este nemate:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas openpyxl
python scripts/01_prepare_data.py
python scripts/02_build_dashboard.py
python scripts/03_prepare_tableau_validation.py
```

## Co potom otvorit

- Pre rychlu kontrolu: `visualization/analyza_dashboard.html`
- Pre navod k Tableau: `tableau/tableau_import_notes_sk.md`
- Pre text do spravy: `report/report_notes_sk.md`

## Co importovat do Tableau

Importujte iba:

- `outputs/cleaned_jazdy.csv`
- `outputs/cleaned_material.csv`
- `outputs/tableau_validation_metrics.csv`

`tableau_validation_metrics.csv` sluzi len na krizovu kontrolu hlavnych KPI.

## Dolezite obmedzenia projektu

- V jazdach je k dispozicii len priama vzdialenost medzi startom a koncom, nie realna trasa po cestach.
- V materialoch su pohyby materialu, nie presny stav skladu.
- Ak sa HTML a Tableau lisia, za finalny vystup sa povazuje validacia v Tableau.
