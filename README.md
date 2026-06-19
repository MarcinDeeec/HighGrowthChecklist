# High-Growth Stock Screener
### MVP zbudowany na bazie checklisty inwestycyjnej

## Struktura projektu

```
screener/
├── data_client.py    # pobieranie danych: FMP (fundamentals) + yfinance (price)
├── metrics.py        # kalkulacja wszystkich wskaźników
├── rules.py          # mapowanie metryk na ✅ / ⚠️ / 🔴 (logika checklisty)
├── scoring.py        # końcowy score i klasyfikacja quality/watchlist/reject
├── main.py           # CLI runner — prawdziwy screener z FMP API
└── demo_run.py       # demo bez API (mock data, offline)
```

## Szybki start

### 1. Instalacja zależności
```bash
pip install pandas numpy requests yfinance
```

### 2. Uruchomienie demo (bez API key)
```bash
python screener/demo_run.py
```

### 3. Konfiguracja FMP API
Zarejestruj się na https://financialmodelingprep.com — plan darmowy daje ~250 req/dzień.

```bash
cp .env.example .env
# wpisz swój klucz do .env
export FMP_API_KEY=<twój_klucz>
```

### 4. Uruchomienie prawdziwego screenera
```bash
python screener/main.py --tickers NVDA CRWD DDOG TTD CELH
python screener/main.py --file tickers.txt --output moje_wyniki.csv
```

## Jak działa scoring

| Kategoria       | Reguły                                       | Wagi |
|-----------------|----------------------------------------------|------|
| Growth          | Revenue YoY ≥ 30%, trend slope               | 3+2  |
| Quality         | Gross margin ≥ 50%, Rule of 40 ≥ 40          | 2+2  |
| Balance sheet   | Debt/Rev ≤ 0.5x, Runway ≥ 12 mies.          | 2+3  |
| Price action    | 6M perf ≤ 200%, 12M perf ≤ 300%, RSI ≤ 75   | 2+1+1|
| Valuation       | EV/Sales ≤ 8x (przy >40% wzr.), P/S ≤ 8x    | 2+1  |
| Management      | Insider sell ratio ≤ 30%                     | 1    |

### Klasyfikacja końcowa

| Label       | Warunki                                                          |
|-------------|------------------------------------------------------------------|
| 🟢 QUALITY  | ≥ 8 zielonych, 0 czerwonych                                     |
| 🟡 WATCHLIST| ≥ 5 zielonych, ≤ 2 czerwone (bez hard red lines)               |
| 🔴 REJECT   | ≥ 3 czerwone LUB hard red line (runway<6M, debt>2x, 6M>200%, RSI>75) |

## Red Lines (auto-reject)
- 🔴 `perf_6m` > 200% w 6 miesięcy
- 🔴 `cash_runway` < 6 miesięcy
- 🔴 `debt_to_revenue` > 2x
- 🔴 `rsi` > 75

## Roadmap (kolejne wersje)
- [ ] Streamlit dashboard z filtrowaniem i sortowaniem
- [ ] FMP Screener endpoint do auto-generowania listy tickerów
- [ ] Alerty emailowe (SMTP) gdy spółka zmieni label
- [ ] Historyczny backtest: czy `quality` bije benchmark?
