# DAT_VIZ — Dokumentácia projektu

---

## 1. Názov projektu

**DAT_VIZ: Vizualizácia a analýza prevádzkových dát — jazdy vozidiel a pohyby materiálu**

---

## 2. Stručná charakteristika projektu

DAT_VIZ je študentský analytický projekt zameraný na spracovanie a vizualizáciu dvoch prevádzkových datasetov: záznamy jázd vozidiel za rok 2024 a záznamy pohybov materiálu za obdobie 2023–2025. Projekt pozostáva z Python skriptov, ktoré načítajú vstupné dáta vo formáte Excel, vyčistia ich, vypočítajú analytické metriky a vygenerujú jeden samostatný HTML súbor s interaktívnym prehľadom výsledkov.

Výstupom projektu je súbor `visualization/index.html`, ktorý obsahuje prehľad KPI metrík, grafy, tabuľky a sekciu pokročilejšej analytiky pre oba datasety. HTML dashboard je navrhnutý ako sprievodný výstup; primárnym nástrojom pre finálnu vizualizáciu je Tableau.

---

## 3. Cieľ projektu

Cieľom projektu je:

- Načítať a spracovať dva heterogénne datasety s rozdielnou štruktúrou, formátom dátumov a kódovaním hodnôt.
- Vypočítať kľúčové metriky pre oba datasety (počty, objemy, podiely, kategórie) spôsobom, ktorý je paritný s výpočtami v Tableau.
- Poskytnúť prehľadný HTML dashboard s grafmi a tabuľkami pre rýchlu kontrolu bez nutnosti otvárať Tableau.
- Realizovať pokročilejšiu analytiku: klasifikáciu anomálií jázd na základe vzťahu motohodín a vzdialenosti a ABC segmentáciu materiálov podľa kumulatívneho podielu objemu.
- Umožniť export vyčistených dát vo formáte CSV pre import do Tableau.

---

## 4. Použité vstupné dáta

### Dataset 1 — Jazdy vozidiel (`dataset_jazdy_2024_cleaned.xlsx`)

Umiestnenie v projekte: `data/clean/dataset_jazdy_2024_cleaned.xlsx`

Dataset obsahuje záznamy jázd 18 vozidiel za rok 2024. Každý riadok predstavuje jeden záznam jazdy. Kód načítava tieto stĺpce:

| Stĺpec | Popis |
|---|---|
| `DATUM` | Dátum jazdy. Normalizuje sa na štandardný kalendárny deň. |
| `SPZ` | Anonymizovaný identifikátor vozidla (18 unikátnych vozidiel). |
| `CAS_OD` / `CAS_DO` | Čas začiatku a konca záznamu, slúžia na výpočet trvania jazdy. |
| `DOBA_STATIA_MIN` | Dĺžka státia medzi jazdami v minútach. |
| `EW_START` / `EL_START` | Zemepisné súradnice startu (surové hodnoty delené 1 000 000 pre prepočet na stupne). Používajú sa na validitu jazdy a hruby odhad polohy. |
| `DIST_START_END_M` | Priama vzdialenosť medzi štartom a koncom jazdy v metroch (nie reálna trasa po cestách). |
| `MOTOHODINY_ZACIATOK` / `MOTOHODINY_KONIEC` / `ROZDIEL_MOTOHODINY` | Motohodiny motora. Konzistencia rozdielov sa overuje pri načítaní. |

Dataset je vo fáze vyčistených dát — predpokladá sa, že predchádzajúci krok prípravy dát (`01_prepare_data.py`) ho pripravil zo surového vstupného súboru.

### Dataset 2 — Pohyby materiálu (`dataset_material_2023_2025.xlsx`)

Umiestnenie v projekte: `data/raw/dataset_material_2023_2025.xlsx`

Dataset obsahuje záznamy pohybov materiálu za obdobie 2023–2025. Podľa overovacích konštánt definovaných priamo v skripte dataset pozostáva z **644 106 riadkov**, pokrýva **690 unikátnych materiálov** a celkový objem pohybov dosahuje **211 935 852 kusových jednotiek**. Kód načítava tieto stĺpce:

| Stĺpec | Popis |
|---|---|
| `DATUM` | Dátum pohybu materiálu. Obsahuje zmesené formáty — časť riadkov je vo formáte natívneho Excel dátumu, časť ako textový reťazec s formátom `dd. mm. yyyy`. Skript obe varianty prekonvertuje na konzistentný timestamp. |
| `MAT_NR` | Kód materiálu. Základ pre DISTINCTCOUNT materiálov, ABC segmentáciu aj rebríček. |
| `MNOZSTVO` | Množstvo pohybu. Môže byť záporné (výdaj), kladné (príjem) alebo nula. Hodnoty sú parsované Tableau-kompatibilnou celočíselnou logikou, ktorá podporuje medzery ako oddeľovač tisícov, záporné hodnoty v zátvorkách aj so záporným znamienkom. |

Projekt podporuje aj voliteľný lookup súbor `RegCis_ciselnik.xlsx`, ktorý by pri dostupnosti doplnil k `MAT_NR` názov materiálu a minimálny stav skladu. V repozitári sa tento súbor nenachádza; bez neho dashboard zobrazuje `MAT_NR` namiesto názvov.

---

## 5. Štruktúra projektu

```
DAT_VIZ/
├── data/
│   ├── clean/
│   │   └── dataset_jazdy_2024_cleaned.xlsx   # vyčistený dataset jázd
│   └── raw/
│       └── dataset_material_2023_2025.xlsx   # surový dataset pohybov materiálu
├── scripts/
│   └── 02_build_dashboard.py                # hlavný skript — generuje HTML dashboard
├── visualization/
│   └── index.html                           # vygenerovaný HTML dashboard (výstup)
├── .venv/                                   # virtuálne prostredie (Python 3.14)
└── README.md
```

**Poznámka k chýbajúcim súborom:** README projektu a záznamy v `__pycache__` naznačujú, že projekt pôvodne obsahoval aj `scripts/01_prepare_data.py`, `scripts/03_prepare_tableau_validation.py` a `scripts/material_quantity_utils.py`. Tieto súbory sa v repozitári v čase zápisu dokumentácie nenachádzajú — ich skompilované `.pyc` súbory sú v `scripts/__pycache__/`, no zdrojové `.py` súbory chýbajú. README tiež odkazuje na adresáre `outputs/`, `tableau/` a `report/`, ktoré v repozitári takisto nie sú prítomné.

---

## 6. Popis hlavných skriptov

### `scripts/02_build_dashboard.py`

Jadro projektu — 4 604-riadkový Python skript, ktorý realizuje kompletný pipeline od načítania dát po vygenerovanie HTML dashboardu. Skript je plne samostatný a neimportuje žiadne vlastné pomocné moduly.

**Vstup:**
- `data/clean/dataset_jazdy_2024_cleaned.xlsx`
- `data/raw/dataset_material_2023_2025.xlsx`
- (voliteľne) `RegCis_ciselnik.xlsx` kdekoľvek v strome projektu — skript ho vyhľadá automaticky

**Výstup:**
- `visualization/index.html` — kompletný HTML dashboard

**Čo skript robí:**

1. **Načítanie a normalizácia dát** — `load_jazdy_dataset()` a `load_material_dataset()` načítajú oba Excel súbory, normalizujú dátumy, časy, súradnice a parsujú množstvá. Pri načítaní sa okamžite overuje konzistencia motohodín (začiatok + rozdiel = koniec).

2. **Parsovanie množstiev materiálu** — `parse_material_quantity_tableau()` realizuje presnú Tableau-paritnú logiku pre stĺpec `MNOZSTVO`: akceptuje celé čísla, čísla s medzerami ako oddeľovačom tisícov a záporné hodnoty zapisané závorkami alebo pomlčkou. Akékoľvek neúspešné parsovanie spôsobí tvrdú chybu (hard failure).

3. **Overovanie dát** — Skript obsahuje sériu `assert_exact()` a `assert_close()` kontrol, ktoré porovnávajú vypočítané hodnoty s hardkódovanými očakávanými konštantami (celkový počet riadkov, počet unikátnych materiálov, celkový objem, mesačný vrchol a i.). Každá odchýlka okamžite zastaví beh a vypíše chybu.

4. **Výpočet analytických pohľadov** — `build_material_views()` vypočítava KPI, mesačné agregáty, ABC segmentáciu a top 10 materiálov. `build_dashboard_data()` následne kombinuje oba datasety do jedného dátového slovníka pre dashboard.

5. **Klasifikácia jázd** — Každá jazda sa zaradí do jednej z 6 vzdialenostných kategórií (Žiadna jazda, Parkovanie, Krátka, Mestská, Regionálna, Diaľková) a zároveň sa overuje Tableau validita na základe startových súradníc (LAT medzi 47–51°, LON medzi 12–23°).

6. **Generovanie HTML** — `build_html()` zostaví kompletný HTML súbor s vloženými dátami ako JSON blob, CSS štýlmi a JavaScript kódom pre interaktívne grafy (canvas-based renderovanie bez externých knižníc). Výsledný súbor je plne samostatný.

### `scripts/01_prepare_data.py` *(chýba v repozitári)*

Podľa README slúži na prípravu a čistenie surových dát. Výstupom mali byť `outputs/cleaned_jazdy.csv` a `outputs/cleaned_material.csv` pre import do Tableau. Zdrojový súbor sa v repozitári nenachádza — prítomný je len skompilovaný `.pyc` v `__pycache__`.

### `scripts/03_prepare_tableau_validation.py` *(chýba v repozitári)*

Podľa README generuje voliteľný validačný export `tableau_validation_metrics.csv`. Zdrojový súbor sa v repozitári nenachádza.

---

## 7. Postup spracovania dát

Pipeline projektu prebieha v týchto krokoch:

**Krok 1 — Príprava dát (skript `01_prepare_data.py`, chýba v repozitári)**
Predpokladaný krok: načítanie surových dát, čistenie, zjednotenie formátov a uloženie výstupov pre Tableau (`outputs/cleaned_jazdy.csv`, `outputs/cleaned_material.csv`). Dataset jázd je v repozitári prítomný vo forme již vyčisteného Excel súboru (`data/clean/`), čo naznačuje, že tento krok prebehol.

**Krok 2 — Načítanie a validácia (`02_build_dashboard.py`)**
- Rides: Dátumy sa parsujú s podporou viacerých textových formátov. Vypočítava sa trvanie jazdy, vzdialenosť v km, klasifikácia do kategórií a flag Tableau validity. Overuje sa konzistencia motohodín.
- Material: Dátumy sa normalizujú s opravou typickej Excel chyby (zámen dňa a mesiaca pri ambivalentných hodnotách ≤ 12). Množstvá sa parsujú Tableau-kompatibilnou logikou. Overuje sa počet riadkov, počet unikátnych materiálov aj celkový objem voči hardkódovaným referenčným hodnotám.

**Krok 3 — Výpočet metrík**
- Jazdy: KPI (počty, podiely, kategórie), agregáty podľa mesiaca, dňa v týždni, vozidla.
- Materiál: KPI (počty, objemy, mediány), mesačné agregáty DISTINCTCOUNT a SUM, ABC segmentácia z kumulatívneho podielu, rebríček top 10 materiálov.

**Krok 4 — Pokročilá analytika**
- Anomálie jázd: každá jazda sa zaradí do jednej zo 4 kategórií podľa kombinácie motohodín a vzdialenosti (prah 500 m).
- ABC deep-dive materiálov: počty materiálov v segmentoch A/B/C a voliteľné porovnanie s minimom skladu z lookup súboru.

**Krok 5 — Generovanie HTML dashboardu**
Všetky vypočítané dáta sa serializujú do JSON a vložia do HTML šablóny. Skript zapíše výsledný súbor do `visualization/index.html`.

**Krok 6 (voliteľný) — Export pre Tableau (`03_prepare_tableau_validation.py`)**
Generovanie `tableau_validation_metrics.csv` ako krížová kontrola metrík pre Tableau.

---

## 8. Spustenie projektu

### Požiadavky

- Python 3.14 (podľa existujúceho `.venv` v repozitári)
- Knižnice: `pandas`, `openpyxl`, `numpy` (README explicitne uvádza `pandas` a `openpyxl`; `numpy` je importovaný v skripte)
- Oba vstupné datasety musia byť na miestach, kde ich skript očakáva:
  - `data/clean/dataset_jazdy_2024_cleaned.xlsx`
  - `data/raw/dataset_material_2023_2025.xlsx`

### Virtuálne prostredie

Repozitár obsahuje priečinok `.venv` s predpripraveným virtuálnym prostredím Python 3.14. Ak chcete použiť existujúce prostredie:

```bash
cd DAT_VIZ
source .venv/bin/activate
```

Ak virtuálne prostredie nefunguje alebo ho chcete vytvoriť odznova:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas openpyxl numpy
```

> **Poznámka:** V repozitári sa nenachádza súbor `requirements.txt`. Zoznam knižníc vychádza z importov v skripte a z pokynov v README.

### Spustenie hlavného skriptu

```bash
source .venv/bin/activate
python scripts/02_build_dashboard.py
```

Skript pri spustení vypíše validačné súhrny na štandardný výstup a nakoniec uloží:

```
visualization/index.html
```

### Otvorenie dashboardu

```bash
xdg-open visualization/index.html
# alebo priamo v prehliadači:
firefox visualization/index.html
```

### Voliteľný krok — validačný export pre Tableau

```bash
python scripts/03_prepare_tableau_validation.py
```

Skript nie je v repozitári prítomný (chýba zdrojový `.py` súbor).

---

### Ako projekt spustiť v skratke

```bash
cd DAT_VIZ
source .venv/bin/activate
python scripts/02_build_dashboard.py
xdg-open visualization/index.html
```

---

### Možné problémy a ich riešenie

| Problém | Príčina | Riešenie |
|---|---|---|
| `ModuleNotFoundError: No module named 'pandas'` | Knižnice nie sú nainštalované v aktívnom prostredí | `pip install pandas openpyxl numpy` |
| `FileNotFoundError: data/clean/dataset_jazdy_2024_cleaned.xlsx` | Vstupný súbor chýba | Umiestniť dataset do `data/clean/` |
| `AssertionError: material total movement rows mismatch` | Dataset bol zmenený alebo sa líši od očakávanej verzie | Overiť, že používate pôvodný dataset — skript overuje presné počty riadkov |
| `ValueError: MOTOHODINY mismatch` | Nekonzistencia motohodín v datasete jázd | Overiť súbor `dataset_jazdy_2024_cleaned.xlsx` |
| Dashboard sa otvorí prázdny | Prehliadač blokuje lokálny JavaScript | Otvoriť cez `file://` alebo spustiť lokálny HTTP server |

---

## 9. Výstupy projektu

**Primárny výstup:**

- `visualization/index.html` — kompletný, samostatný HTML dashboard. Neobsahuje žiadne externé závislosti (CSS, JavaScript ani dáta nie sú načítavané zo siete). Súbor je prenositeľný a otvoriteľný bez internetového pripojenia.

**Vedľajšie výstupy (podľa README, v repozitári nie sú prítomné):**

- `outputs/cleaned_jazdy.csv` — vyčistené dáta jázd pre import do Tableau
- `outputs/cleaned_material.csv` — vyčistené dáta pohybov materiálu pre import do Tableau
- `tableau_validation_metrics.csv` — voliteľný validačný export z `03_prepare_tableau_validation.py`

---

## 10. Pokročilejšia analytika

Dashboard obsahuje samostatnú sekciu pokročilejšej analytiky s dvoma analytickými pohľadmi.

### Anomálie jázd — vzťah motohodín a vzdialenosti

**Analytická otázka:** Ktoré jazdy naznačujú neefektívnu prevádzku, státie s bežiacim motorom alebo GPS/telemetrickú nekonzistenciu?

Každá jazda sa zaradí do jednej zo štyroch kategórií na základe kombinácie hodnôt `ROZDIEL_MOTOHODINY` a `DIST_START_END_M`:

| Kategória | Podmienka | Interpretácia |
|---|---|---|
| **Normálna jazda** | Motohodiny > 0 a vzdialenosť ≥ 500 m | Bežný presun bez zjavného signálu nekonzistencie |
| **Motor beží, auto stojí** | Motohodiny > 0 a vzdialenosť < 500 m | Nakládka, čakanie, hydraulika, voľnobeh alebo iná stacionárna prevádzka |
| **Pohyb bez motohodín** | Motohodiny = 0 a vzdialenosť ≥ 500 m | Telemetrický nesúlad, chýbajúci CAN, ťahanie alebo nekonzistentný záznam |
| **Nulová jazda (GPS ping)** | Motohodiny = 0 a vzdialenosť < 500 m | GPS/telemetrický ping bez reálnej jazdy |

Prah pre minimálny pohyb je 500 m. Nulová hodnota motohodín sa vyhodnocuje s malým epsilon (`1e-9`) na odfilterovanie číselných artefaktov po načítaní z Excelu. Výstup je podklad pre interpretáciu a manuálny review, nie automatický dôkaz prevádzkového problému. Dashboard zobrazuje súhrnné karty, stĺpcový graf, tabuľku kategórií s podielmi a prehľad per vozidlo.

### ABC segmentácia materiálov

**Analytická otázka:** Ako sa celkový objem pohybov rozdeľuje medzi ABC segmenty a ktoré materiály nesú najväčší objem?

Pre každý `MAT_NR` sa spočíta celkové parsované množstvo. Materiály sa zostupne zoradia a segmenty sa priraďujú na základe kumulatívneho podielu:

- **Segment A:** prvých 80 % celkového objemu
- **Segment B:** nasledujúcich 15 % (80–95 %)
- **Segment C:** zvyšných 5 %

Dashboard zobrazuje donut graf podielov, tabuľku ABC segmentov s počtami materiálov a top 10 materiálov podľa objemu. Ak je dostupný lookup `RegCis_ciselnik.xlsx`, zobrazí sa navyše porovnanie priemerného množstva s minimom skladu pre materiály, kde je deficit.

---

## 11. Publikovanie projektu

Vygenerovaný súbor `visualization/index.html` je samostatný HTML dokument bez externých závislostí, čo ho robí vhodným na publikovanie cez GitHub Pages.

**Postup publikovania cez GitHub Pages:**

1. Súbor `visualization/index.html` je potrebné premenovať alebo skopírovať tak, aby bol dostupný pod adresou, ktorú GitHub Pages očakáva.
2. V nastaveniach repozitára (`Settings → Pages`) zvoliť vetvu `main` a ako zdrojový adresár vybrať `/docs` (ak bol dashboard skopírovaný tam) alebo root repozitára.
3. Alternatívne je možné nastaviť zdrojový adresár na `/visualization` — GitHub Pages podporuje aj vlastné adresáre.
4. Po uložení nastavení bude dashboard dostupný na adrese `https://<username>.github.io/<repo-name>/`.

Keďže dashboard neobsahuje žiadne externé volania ani závislosti, funguje spoľahlivo ako statická stránka bez potreby servera.

---

## 12. Limity projektu

- **Iba priama vzdialenosť jázd:** `DIST_START_END_M` vyjadruje vzdialenosť vzdušnou čiarou medzi štartom a koncom jazdy, nie reálnu trasu po cestách. Metriky vzdialenosti sú teda len hrubým odhadom.

- **Pohyby materiálu ≠ stav skladu:** Dataset zachytáva pohyby (príjmy a výdaje), nie aktuálny stav zásob v čase. Smer pohybu je odvodený iba zo znamienka hodnoty `MNOZSTVO`, nie z explicitného typového poľa.

- **Chýbajúce skripty v repozitári:** Zdrojové súbory `01_prepare_data.py`, `03_prepare_tableau_validation.py` a `material_quantity_utils.py` sa v repozitári nenachádzajú — prítomné sú iba ich skompilované `.pyc` verzie. Kroky prípravy dát a validačného exportu pre Tableau nie je možné zopakovať bez týchto skriptov.

- **Chýbajúce výstupné CSV súbory:** Adresár `outputs/` s exportmi pre Tableau nie je v repozitári prítomný.

- **Manuálne umiestnenie datasetov:** Vstupné súbory musia byť manuálne umiestnené na presné cesty, ktoré skript očakáva. Neexistuje žiaden automatický mechanizmus stiahnutia alebo kontroly dát.

- **Hardkódované validačné konštanty:** Skript overuje výpočty voči presne definovaným hodnotám (644 106 riadkov, 690 materiálov atď.). Akákoľvek zmena vstupného datasetu si vyžaduje aktualizáciu týchto konštánt v kóde.

- **Chýbajúci lookup materiálov:** Bez súboru `RegCis_ciselnik.xlsx` dashboard nezobrazuje názvy materiálov ani porovnanie s minimom skladu. Dashboard sa s týmto stavom vyrovná bez chyby, ale analytická hodnota je obmedzená.

- **Statický HTML výstup:** Dashboard nevykonáva žiadne live dopytovanie dát. Každá zmena vstupov si vyžaduje opätovné spustenie skriptu.

- **Chýbajúci `requirements.txt`:** Zoznam závislostí nie je explicitne definovaný v súbore `requirements.txt`. Inštalácia knižníc sa riadi pokynmi v README.

---

## 13. Záver

Projekt DAT_VIZ realizuje kompletný analytický pipeline od načítania surových Excel dát po vygenerovanie samostatného HTML dashboardu. Skript `02_build_dashboard.py` spracováva dva prevádzkovo odlišné datasety — záznamy jázd vozidiel a pohyby materiálu — a vykonáva ich normalizáciu, validáciu aj analytické agregácie s dôrazom na paritu výsledkov s Tableau. Pokročilejšia analytika klasifikuje jazdy do štyroch kategórií podľa vzťahu motohodín a vzdialenosti a realizuje kumulatívnu ABC segmentáciu materiálov. Výsledný dashboard je prenositeľný, nevyžaduje pripojenie k internetu a je možné ho publikovať cez GitHub Pages. Projekt má jasne definované limity vyplývajúce z povahy vstupných dát — predovšetkým absencia reálnych trás jázd a nemožnosť odvodiť presný stav skladu z pohybových záznamov.
