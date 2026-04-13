# Tableau - prakticky import

Tento projekt ma mat v Tableau dva jednoduche dashboardy. Nepouzivajte HTML ako nahradu Tableau.

## 1. Co importovat

Importujte tieto subory z priecinka `outputs/`:

- `cleaned_jazdy.csv`
- `cleaned_material.csv`
- `tableau_validation_metrics.csv`

## 2. Dashboard 1 - Jazdy vozidiel

Nazov dashboardu:

- `Jazdy vozidiel 2024`

Pouzity zdroj:

- `cleaned_jazdy.csv`

KPI:

- Celkovy pocet zaznamov
- Pocet vozidiel
- Platne jazdy (`near_zero_trip = False`)
- Potencialne neefektivne zaznamy (`potentially_inefficient_trip = True`)

Grafy:

- Pocet zaznamov podla `year_month`
- Pocet zaznamov podla `weekday_sk`
- Pocet zaznamov podla `vehicle_id`
- Rozdelenie podla `near_zero_trip` alebo podla pasiem `distance_km`

Filtre:

- `year_month`
- `vehicle_id`
- `near_zero_trip`

Poznamka do komentara:

- Pri interpretacii povedzte, ze `distance_km` je len priama vzdialenost medzi startom a koncom, nie presna trasa po cestach.

## 3. Dashboard 2 - Zasobovanie materialmi

Nazov dashboardu:

- `Zasobovanie materialmi 2023-2025`

Pouzity zdroj:

- `cleaned_material.csv`

KPI:

- Celkovy pocet pohybov
- Pocet materialov
- Celkove mnozstvo
- Priemerne mnozstvo

Grafy:

- Pocet pohybov podla `year_month`
- Celkove mnozstvo podla `year_month`
- Pocet pohybov podla `material_prefix`
- Pocet unikatnych materialov podla `abc_segment`

Filtre:

- `year_month`
- `material_prefix`
- `material_number`
- `abc_segment`

Poznamka do komentara:

- Povedzte, ze ide o analyzu pohybov materialu, nie o presny vypocet skladovych zasob.

## 4. Co porovnat s validation CSV

V `tableau_validation_metrics.csv` skontrolujte hlavne tieto hodnoty:

- jazdy / `celkovy_pocet_zaznamov`
- jazdy / `pocet_vozidiel`
- jazdy / `platne_jazdy_over_50m`
- jazdy / `near_zero_zaznamy`
- jazdy / `priemer_km_na_platnu_jazdu`
- jazdy / `potencialne_neefektivne_zaznamy`
- material / `celkovy_pocet_pohybov`
- material / `pocet_materialov`
- material / `celkove_mnozstvo`
- material / `priemerne_mnozstvo`
- material / `median_mnozstva`
- material / `abc_segment_a_materialy`

## 5. Co povedat, ak sa HTML a Tableau lisia

Ak sa hodnoty lisia:

- najprv skontrolujte filtre
- potom skontrolujte typ pola datum / datetime
- potom skontrolujte, ci pouzivate `COUNT` alebo `COUNTD`

Do spravy alebo na obhajobe povedzte:

- HTML je len doplnkovy vystup generovany z Python pipeline
- finalna validacia bola spravena v Tableau
- pri nezhode ma prednost Tableau po kontrole definicie metriky
