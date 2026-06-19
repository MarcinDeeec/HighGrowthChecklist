# High-Growth Stock Screener

MVP screenera akcji wzrostowych oparty na checkliście inwestycyjnej.
**Nowa architektura: yfinance + Finviz — bez żadnego klucza API.**

```
[discovery: Finviz]  -->  ticker  -->  data_client  -->  metrics  -->  rules (🟢/⚠️/🔴)  -->  scoring  -->  CSV
                                      (yfinance + Finviz)
```

## Podział pracy między źródłami

Każde źródło robi to, w czym jest najlepsze:

| Zadanie | Źródło | Dlaczego |
|---|---|---|
| **Discovery** (skan całego rynku → lista kandydatów) | **Finviz** (`finvizfinance`) | jedno zapytanie filtruje ~11 000 spółek US, bez klucza i bez limitu |
| **Fundamentals kwartalne** (income / balance / cashflow, trendy) | **yfinance** | pełne szeregi kwartalne potrzebne do YoY, runway, debt/rev |
| **Ceny / RSI-14 / performance 6M·12M** | **yfinance** | precyzyjne liczenie z historii cen |
| **Insider transactions** | **yfinance** | `Ticker.insider_transactions` (Yahoo → SEC Form 4) |
| **Snapshot wycen** (P/S, PEG, P/E, marże) | **yfinance `.info`** + **Finviz** (fallback) | `.info` daje gotowe wskaźniki; Finviz uzupełnia braki |

> Cała logika metryk/reguł/scoringu operuje na jednym, stabilnym **kontrakcie danych**
> (styl Alpha Vantage). `data_client.py` tłumaczy na niego dane z yfinance i Finviz,
> więc `metrics.py` / `rules.py` / `scoring.py` pozostają niezmienione.

## Struktura projektu

```
screener/
├── discovery.py     # Finviz: skan rynku -> lista tickerów (presety + własne filtry)
├── data_client.py   # yfinance (fundamentals/ceny/insider) + Finviz (snapshot) -> kontrakt
├── metrics.py       # czyste obliczenia metryk
├── rules.py         # mapowanie metryk na 🟢 / ⚠️ / 🔴 + red lines
├── scoring.py       # ważony scoring i klasyfikacja quality/watchlist/reject
├── main.py          # CLI runner + discovery + eksport CSV
├── demo_run.py      # demo offline pipeline'u na danych mock
├── demo_adapter.py  # offline test adapterów yfinance/Finviz -> kontrakt
├── requirements.txt
├── tickers.txt      # przykładowa lista tickerów dla --file
└── .env.example     # OPCJONALNE ustawienia (klucz NIE jest potrzebny)
```

## Instalacja

Wymagany Python 3.9+ (działa też na 3.13). Zalecane wirtualne środowisko.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Klucz API nie jest potrzebny** — yfinance i Finviz działają bez rejestracji.

## Uruchomienie

### 1. Discovery — znajdź kandydatów z rynku i od razu ich oceń

```bash
# preset 'growth' (Finviz), max 30 spółek
python main.py --discover growth --limit 30 --output wyniki.csv

# własne filtry Finviz
python main.py --discover-filters "Country=USA" "Sector=Technology" --limit 50
```

Dostępne presety: `growth`, `high_growth`, `hypergrowth` (zob. `discovery.PRESETS`).

### 2. Konkretne tickery

```bash
python main.py --tickers NVDA CRWD DDOG NET --output wyniki.csv
python main.py --file tickers.txt --output wyniki.csv
python main.py --tickers NVDA --no-verbose
```

### 3. Demo offline (bez sieci)

```bash
python demo_run.py        # pipeline na danych mock
python demo_adapter.py    # test adapterów yfinance/Finviz -> kontrakt danych
```

## Co liczy screener

| Metryka | Źródło | Reguła (🟢 / ⚠️ / 🔴) |
|---|---|---|
| Revenue growth YoY | yfinance (Finviz fallback) | >30% / 10–30% / <10% lub spadek |
| Trend revenue (kwartały) | yfinance | slope ≥ 0 / slope < 0 / — |
| Gross margin | yfinance | >50% / 30–50% / <30% |
| Operating margin | yfinance / `.info` | dodatnia / lekka strata / głęboka strata |
| Rule of 40 | metrics | ≥40 / 20–40 / <20 |
| Debt-to-revenue | yfinance | ≤0.5x / 0.5–2x / **>2x (red line)** |
| Cash runway (mies.) | yfinance | ≥12 / 6–12 / **<6 (red line)** |
| Valuation (EV/Sales→P/S) | yfinance `.info` / Finviz | rozsądna / premium / ekstremalna |
| PEG (opcjonalnie) | yfinance `.info` / Finviz | ≤1.5 / 1.5–3 / >3 |
| 6M performance | yfinance | ≤100% / 100–200% / **>200% (red line)** |
| 12M performance | yfinance | ≤100% / 100–300% / **>300% (red line)** |
| RSI-14 | yfinance | ≤70 / 70–75 / **>75 (red line)** |
| Pre-revenue | yfinance / `.info` | przychody OK / — / **brak przychodów (red line)** |
| Insider transactions | yfinance | kupują netto / przewaga sprzedaży / silna wyprzedaż |

### Klasyfikacja końcowa

| Etykieta | Warunki |
|---|---|
| 🟢 QUALITY | ≥ 8 zielonych, 0 czerwonych, brak hard red line |
| 🟡 WATCHLIST | wynik mieszany, ≤ 2 czerwone, brak hard red line |
| 🔴 REJECT | ≥ 3 czerwone **lub** dowolna hard red line |

**Hard red lines** (twarde veto — ticker nie może być QUALITY): `debt > 2x revenue`,
`runway < 6 miesięcy`, `6M > 200%`, `12M > 300%`, `RSI > 75`, `pre-revenue`.

Scoring jest ważony — największe wagi mają **revenue growth (3)**, **cash runway (3)**
i **debt-to-revenue (3)**. Sygnał `N/A` (brak danych) jest neutralny: nie wlicza się
ani do punktów, ani do mianownika.

## Ograniczenia i uwagi

- **yfinance jest nieoficjalne** (Yahoo) — dla części spółek dane kwartalne bywają
  niepełne lub puste; wtedy dana metryka = `N/A` (bez crasha). Jakość fundamentów
  bywa gorsza niż dane prosto z raportów SEC.
- **Trend przychodów** wymaga wielu kwartałów; yfinance zwykle daje ~4–5 kwartałów,
  więc trend YoY często wychodzi `N/A` (neutralnie). Sam YoY ma fallback z `.info`.
- **Finviz** dane są opóźnione ~15 min i to głównie snapshot (bez szeregów kwartalnych) —
  dlatego służy do discovery i uzupełnienia wycen, a nie do trendów.
- **Etykiety filtrów Finviz** w `discovery.PRESETS` pochodzą z UI Finviz i mogą się
  zmieniać. Jeśli preset przestanie działać, zaktualizuj słownik lub podaj własny
  `--discover-filters`. Podgląd dostępnych filtrów: `discovery.available_filters()`.
- **Rate-limit:** brak twardego limitu dziennego jak w Alpha Vantage, ale zbyt szybkie
  zapytania mogą skutkować chwilową blokadą IP. Reguluj `SCREENER_PAUSE` / `--delay`.
- Pytania jakościowe z checklisty (koncentracja klientów, TAM, moat) nadal wymagają
  ręcznej oceny — screener automatyzuje część ilościową + red lines + insider.

## Dalszy rozwój (pomysły)

- Lokalny cache odpowiedzi yfinance/Finviz (mniej zapytań, szybsze powtórki).
- Pre-filtr techniczny w discovery (RSI / performance) jeszcze przed pełnym scoringiem.
- Testy jednostkowe `rules.py` / `scoring.py` (mocki są już w `demo_run.py` / `demo_adapter.py`).
- Eksport do Excela z kolorowaniem sygnałów.
