#!/usr/bin/env python3
"""
main.py — uruchomienie screenera i eksport wyników
Użycie:
    python main.py --tickers NVDA CRWD DDOG TTD --output results.csv
    python main.py --file tickers.txt
"""
import argparse
import sys
import time
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import data_client as dc
import metrics as met
import rules as rl
import scoring as sc


DEFAULT_TICKERS = ["NVDA", "CRWD", "DDOG", "TTD", "CELH", "SHOP", "NET", "AFRM"]


def screen_ticker(ticker: str, verbose: bool = True) -> dict | None:
    try:
        income_df = dc.get_income_statements(ticker)
        balance_df = dc.get_balance_sheet(ticker)
        metrics_df = dc.get_key_metrics(ticker)
        cashflow_df = dc.get_cash_flow(ticker)
        price_df = dc.get_price_history(ticker, period="1y")
        insider_df = dc.get_insider_trades(ticker)

        if income_df.empty and balance_df.empty and metrics_df.empty:
            raise RuntimeError("Brak fundamentals z API — pusty response.")

        m = met.compute_all(
            ticker,
            income_df,
            balance_df,
            metrics_df,
            cashflow_df,
            price_df,
            insider_df
        )

        rules_eval = rl.evaluate_all(m)
        score_result = sc.compute_score(rules_eval)

        if verbose:
            print(sc.format_report(ticker, m, rules_eval, score_result))

        row = {**m, **score_result}
        for rule_name, (signal, reason) in rules_eval.items():
            row[f"sig_{rule_name}"] = signal
            row[f"reason_{rule_name}"] = reason

        return row

    except Exception as e:
        print(f"⚠️  Błąd dla {ticker}: {e}")
        return {
            "ticker": ticker,
            "label": "error",
            "pct": None,
            "greens": None,
            "warnings": None,
            "reds": None,
            "error": str(e),
        }


def run(tickers: list[str], output_path: str, delay: float = 1.0, verbose: bool = True):
    results = []

    for i, ticker in enumerate(tickers):
        print(f"\n[{i+1}/{len(tickers)}] Przetwarzam: {ticker}")
        row = screen_ticker(ticker, verbose=verbose)
        if row:
            results.append(row)
        time.sleep(delay)

    if not results:
        print("Brak wyników.")
        return

    df = pd.DataFrame(results)

    if "pct" not in df.columns:
        df["pct"] = None
    if "label" not in df.columns:
        df["label"] = "error"

    order = {"quality": 0, "watchlist": 1, "reject": 2, "error": 3}
    df["_sort"] = df["label"].map(order).fillna(3)

    df = df.sort_values(
        ["_sort", "pct"],
        ascending=[True, False],
        na_position="last"
    ).drop(columns=["_sort"])

    df.to_csv(output_path, index=False)
    print(f"\n✅ Wyniki zapisane do: {output_path}")

    print("\n" + "=" * 60)
    print("RANKING PODSUMOWANIE")
    print("=" * 60)

    summary_cols = [
        "ticker", "label", "pct", "greens", "warnings", "reds",
        "revenue_growth_yoy", "gross_margin", "ev_to_sales", "perf_6m", "rsi_14", "error"
    ]
    available = [c for c in summary_cols if c in df.columns]

    if available:
        print(df[available].to_string(index=False))
    else:
        print(df.to_string(index=False))

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="High-Growth Stock Screener")
    parser.add_argument("--tickers", nargs="+", help="Lista tickerów", default=None)
    parser.add_argument("--file", type=str, help="Plik .txt z tickerami (jeden na linię)")
    parser.add_argument("--output", type=str, default="screener_results.csv")
    parser.add_argument("--delay", type=float, default=1.2, help="Opóźnienie między requestami (s)")
    parser.add_argument("--no-verbose", action="store_true")
    args = parser.parse_args()

    if args.file:
        with open(args.file) as f:
            tickers = [line.strip().upper() for line in f if line.strip()]
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        print(f"Brak tickerów — używam domyślnej listy: {DEFAULT_TICKERS}")
        tickers = DEFAULT_TICKERS

    run(
        tickers=tickers,
        output_path=args.output,
        delay=args.delay,
        verbose=not args.no_verbose
    )


if __name__ == "__main__":
    main()