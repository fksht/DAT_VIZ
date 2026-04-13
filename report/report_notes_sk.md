# Poznamky k sprave

## Úvod

Cielom projektu je jednoducha a obhajitelna analyza dvoch datasetov: zaznamov o jazdach vozidiel za rok 2024 a zaznamov o pohyboch materialu za roky 2023 az 2025. Hlavna cast odovzdania je pripravena pre Tableau. HTML vystup je len doplnok a sluzi na rychly prehlad.

## Popis datasetov

### Dataset jazdy

- povodny subor: `data/raw/dataset_jazdy_2024.xlsx`
- povodne polia: datum, rok, vozidlo, cas od/do, start a koniec polohy, doba statia, motohodiny, vzdialenost medzi startom a koncom
- rozsah: 11 601 zaznamov, 18 vozidiel, rok 2024

### Dataset material

- povodny subor: `data/raw/dataset_material_2023_2025.xlsx`
- povodne polia: datum, rok, cislo materialu, mnozstvo
- rozsah: 644 106 zaznamov, 690 materialov, roky 2023 az 2025

## Pochopenie dát

Pri datasete jazd je dolezite, ze pole `DIST_START_END_M` nepredstavuje realnu trasu po cestach, ale len priamu vzdialenost medzi zaciatocnym a koncovym bodom. Dataset preto umoznuje porovnat aktivitu vozidiel, vyvoj v case a heuristicky hladat zvlastne zaznamy, ale neumoznuje bezpecne tvrdit nic o presnych trasach alebo adresach.

Pri datasete materialu ide o pohyby materialu. Zaznamy umoznuju sledovat objem a frekvenciu pohybov v case a vytvorit jednoduchu segmentaciu materialov. Dataset vsak neobsahuje smer pohybu, cenu ani presny stav skladu.

## Obmedzenia dát

### Jazdy

- zmiesany format datumov v raw Exceli
- suradnice mali zmiesany pocet cislic a bolo ich treba standardizovat
- 2 zaznamy ostali bez validnej startovacej polohy
- vysoka cast zaznamov ma posun pod 50 m, preto nemaju byt automaticky interpretovane ako bezna jazda
- nie su k dispozicii adresy, dovod jazdy ani realna trasa

### Material

- zmiesany format datumov v raw Exceli
- cast mnozstiev bola zapisovana s desatinnou ciarkou
- nie je uvedena jednotka mnozstva
- nie je uvedeny smer pohybu
- dataset neumoznuje presny vypocet skladovych zasob v case

## Deskriptívna analýza

### Jazdy

- celkovy pocet zaznamov: 11 601
- pocet vozidiel: 18
- platne jazdy nad 50 m: 5 248
- near-zero zaznamy pod 50 m: 6 353
- priemerna priama vzdialenost na platnu jazdu: 12,39 km
- median priamej vzdialenosti na platnu jazdu: 2,11 km
- najviac zaznamov ma vozidlo SPZ26 (902), najmenej SPZ14 (341)

### Material

- celkovy pocet pohybov: 644 106
- pocet materialov: 690
- celkove mnozstvo: 177 585 193
- priemerne mnozstvo na pohyb: 275,7
- median mnozstva na pohyb: 9,0
- analyza sa tyka pohybov materialu, nie zasob na sklade

## Pokročilejšia analytika

### Jazdy - heuristicky oznacene potencialne neefektivne zaznamy

Ako pokrocilejsia analyza bola zvolena jednoducha heuristika: zaznam je oznaceny ako potencialne neefektivny, ak ma trvanie aspon 30 minut a priama vzdialenost medzi startom a koncom je mensia ako 0,5 km, pricom nejde o near-zero zaznam pod 50 m. Takto bolo oznacenych 308 zaznamov. Tento vysledok nepredstavuje dokaz neefektivity, iba signal na dalsiu kontrolu.

### Material - ABC segmentacia

Pri materialoch bola ako pokrocilejsia analyza zvolena ABC segmentacia podla kumulativneho podielu na celkovom mnozstve. Vysledok je:

- segment A: 32 materialov
- segment B: 70 materialov
- segment C: 588 materialov

Tento pristup je zvoleny preto, ze je jednoduchy, interpretovatelny a dobre obhajitelny aj bez ceny materialov alebo detailov o sklade.

## Využitie AI nástrojov

AI bola pouzita len ako podpora pri:

- navrhu cistenia dat
- navrhu bezpecnych metrik
- navrhu struktury HTML prehladu
- navrhu osnovy reportu

Finalne vystupy boli znovu prepocitane skriptami nad raw Excel subormi a validovane cez Tableau.

## Validácia voči Tableau

Pre Tableau boli pripravene dva cleaned CSV subory a samostatny subor `tableau_validation_metrics.csv`. V Tableau sa porovnavaju hlavne pocty zaznamov, pocty entit, priemerne mnozstva a zakladne hodnoty pre pokrocilejsiu analyzu. Ak sa nejaka hodnota lisi, kontroluje sa definicia metriky, filtre a typ pola.

## Porovnanie Tableau vs HTML/AI výstup

HTML vystup je doplnkovy a je generovany z rovnakej Python pipeline ako validation CSV. Nepredstavuje povinnu cast zadania. Finalne a obhajitelne vysledky su tie, ktore sa daju zreprodukovat v Tableau po importe cleaned CSV suborov. Ak by sa HTML a Tableau lisili, prednost ma Tableau po kontrole definicie metriky.

## Čo AI navrhla a čo bolo po validácii potrebné opraviť

Po validacii bolo potrebne spravit tieto upravy:

- zjednodusit pipeline na tri jasne skripty
- odstranit pomocne exporty, ktore neboli nutne pre odovzdanie
- opravit parser suradnic, lebo cast raw hodnot mala rozny pocet cislic
- vypustit menej obhajitelny clustering a nechat len jednoduchsie ABC segmentovanie
- ponechat pri jazdach len heuristiku, ktoru vieme presne vysvetlit z dostupnych poli
- v texte dosledne oddelit to, co data podporuju, od toho, co by bolo len domnienkou

## Záver a odporúčania

Projekt ukazuje, ze oba datasety umoznuju jednoduchu deskriptivnu analyzu a aspon jednu zmysluplnu pokrocilejsiu analyzu bez toho, aby bolo potrebne prehanat zavery. Pri jazdach je najdolezitejsie oddelit near-zero zaznamy od beznej aktivity a pri materialoch jasne povedat, ze ide o pohyby, nie o skladove stavy. Na obhajobe je vhodne zdoraznit, ze finalne KPI a grafy boli validovane v Tableau a ze projekt bol zamerne zjednoduseny na minimalnu, ale korektnu podobu.
