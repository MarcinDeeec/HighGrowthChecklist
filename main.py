#!/usr/bin/env python3
"""
main.py
=======
CLI runner screenera high-growth stocks (zrodla: yfinance + Finviz).

Tryby wejscia:
    # konkretne tickery
    python main.py --tickers NVDA CRWD DDOG NET --output wyniki.csv
    # tickery z pliku
    python main.py --file tickers.txt --output wyniki.csv
    # DISCOVERY: znajdz kandydatow z calego rynku przez Finviz, potem ocen
    python main.py --discover growth --limit 30 --output wyniki.csv
    python main.py --discover-filters "Country=USA" "Sector=Technology" --limit 50

Pipeline dla kazdego tickera:
    data_client.fetch_all -> metrics.compute_all -> rules.evaluate_all
    -> scoring.compute_score -> wiersz wynikow

Program NIE crashuje przy brakach danych (None / N/A) ani przy bledach zrodla:
  - braki -> pola None, sygnaly 'na'
  - rate-limit / blad -> komunikat + przejscie do kolejnego tickera
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_client as dc
import discovery as disc
import metrics as met
import rules as rl
import scoring as sc

DEFAULT_TICKERS = ["NVDA", "CRWD", "DDOG", "NET"]


def screen_ticker(ticker: str, verbose: bool = True) -> dict:
    """Przetwarza jeden ticker. Zawsze zwraca wiersz (nawet przy bledzie)."""
    try:
        data = dc.fetch_all(ticker)
    except dc.RateLimitError as e:
        print(f"  \u23F8\uFE0F  Rate-limit dla {ticker}: {e}")
        return {"ticker": ticker, "label": "error", "error": f"rate_limit: {e}"}
    except dc.ScreenerDataError as e:
        print(f"  \u26A0\uFE0F  Blad danych dla {ticker}: {e}")
        return {"ticker": ticker, "label": "error", "error": str(e)}
    except Exception as e:  # ostatnia linia obrony — nie wywalamy calego biegu
        print(f"  \u26A0\uFE0F  Nieoczekiwany blad dla {ticker}: {e}")
        return {"ticker": ticker, "label": "error", "error": str(e)}

    # Brak jakichkolwiek fundamentals = nie ma czego liczyc.
    if (data["income"].empty and data["balance"].empty
            and data["cashflow"].empty and not data["overview"]):
        print(f"  \u26A0\uFE0F  Brak fundamentals dla {ticker} (puste zrodla).")
        return {"ticker": ticker, "label": "error", "error": "no_fundamentals"}

    metrics = met.compute_all(ticker, data)
    rules_eval = rl.evaluate_all(metrics)
    score = sc.compute_score(rules_eval)

    if verbose:
        print(sc.format_report(ticker, metrics, rules_eval, score))

    row = {**metrics, **score}
    for rule_name, (signal, reason) in rules_eval.items():
        row[f"sig_{rule_name}"] = signal
        row[f"reason_{rule_name}"] = reason
    return row


def run(tickers, output_path: str, delay: float = 0.0, verbose: bool = True) -> None:
    results = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, start=1):
        print(f"\n[{i}/{total}] Przetwarzam: {ticker}")
        results.append(screen_ticker(ticker, verbose=verbose))
        if delay and i < total:
            time.sleep(delay)

    if not results:
        print("Brak wynikow.")
        return

    df = pd.DataFrame(results)
    if "label" not in df.columns:
        df["label"] = "error"
    if "pct" not in df.columns:
        df["pct"] = None

    order = {"quality": 0, "watchlist": 1, "reject": 2, "error": 3}
    df["_sort"] = df["label"].map(order).fillna(3)
    df = (df.sort_values(["_sort", "pct"], ascending=[True, False], na_position="last")
            .drop(columns=["_sort"]))

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n\u2705 Wyniki zapisane do: {output_path}")

    print("\n" + "=" * 64)
    print(" RANKING")
    print("=" * 64)
    summary_cols = ["ticker", "label", "pct", "greens", "warnings", "reds",
                    "revenue_growth_yoy", "gross_margin", "ev_to_sales",
                    "perf_6m", "rsi_14", "insider_net_ratio", "error"]
    available = [c for c in summary_cols if c in df.columns]
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(df[available].to_string(index=False) if available else df.to_string(index=False))
    print("=" * 64)


def _parse_kv(pairs):
    """['Country=USA', 'Sector=Technology'] -> {'Country':'USA','Sector':'Technology'}."""
    out = {}
    for item in pairs or []:
        if "=" not in item:
            print(f"\u26A0\uFE0F  Pomijam filtr bez '=': {item}")
            continue
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="High-Growth Stock Screener (yfinance + Finviz)")
    p.add_argument("--tickers", nargs="+", help="Lista tickerow, np. --tickers NVDA CRWD DDOG")
    p.add_argument("--file", type=str, help="Plik .txt z tickerami (jeden na linie)")
    p.add_argument("--discover", nargs="?", const="growth", default=None,
                   help=f"Discovery przez Finviz wg presetu. Dostepne: {disc.list_presets()}. "
                        "Bez wartosci uzywa 'growth'.")
    p.add_argument("--discover-filters", nargs="+", dest="discover_filters",
                   help="Wlasne filtry Finviz, np. --discover-filters \"Country=USA\" \"Sector=Technology\"")
    p.add_argument("--signal", type=str, default=None, help="Sygnal Finviz (np. 'Top Gainers')")
    p.add_argument("--order", type=str, default=None, help="Pole sortowania Finviz w discovery")
    p.add_argument("--limit", type=int, default=None, help="Limit liczby tickerow z discovery")
    p.add_argument("--output", type=str, default="wyniki.csv", help="Sciezka CSV (domyslnie wyniki.csv)")
    p.add_argument("--delay", type=float, default=0.0,
                   help="Dodatkowe opoznienie miedzy tickerami w sekundach")
    p.add_argument("--no-verbose", action="store_true", help="Nie drukuj szczegolowych raportow")
    return p.parse_args(argv)


def load_tickers(args: argparse.Namespace):
    if args.tickers:
        return [t.strip().upper() for t in args.tickers]
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"\u26A0\uFE0F  Plik {args.file} nie istnieje.")
            return []
        with path.open(encoding="utf-8") as f:
            return [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
    if args.discover or args.discover_filters:
        filters = _parse_kv(args.discover_filters) if args.discover_filters else None
        preset = args.discover if isinstance(args.discover, str) else None
        print(f"\U0001F50E Discovery (Finviz): preset={preset or '(wlasne filtry)'} limit={args.limit}")
        tickers = disc.discover(preset=preset, filters=filters, signal=args.signal,
                                order=args.order, limit=args.limit)
        if not tickers:
            print("\u26A0\uFE0F  Discovery nie zwrocilo tickerow (sprawdz filtry / dostepnosc Finviz).")
        else:
            print(f"   Znaleziono {len(tickers)} kandydatow: {', '.join(tickers[:15])}"
                  + (" ..." if len(tickers) > 15 else ""))
        return tickers
    print(f"Brak tickerow — uzywam domyslnej listy: {DEFAULT_TICKERS}")
    return list(DEFAULT_TICKERS)


def main(argv=None) -> int:
    args = parse_args(argv)
    tickers = load_tickers(args)
    if not tickers:
        print("Brak tickerow do przetworzenia.")
        return 1
    run(tickers, output_path=args.output, delay=args.delay, verbose=not args.no_verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
