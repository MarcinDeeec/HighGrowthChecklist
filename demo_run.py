#!/usr/bin/env python3
"""
demo_run.py
===========
Demo offline — uruchamia caly pipeline (metrics -> rules -> scoring) na danych
MOCK, bez klucza Alpha Vantage i bez sieci. Sluzy do szybkiego sprawdzenia
logiki oraz jako przyklad ksztaltu danych oczekiwanych przez metrics.compute_all().

Uruchom:  python demo_run.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import metrics as met
import rules as rl
import scoring as sc


# ── Fabryki danych mock w formacie zgodnym z Alpha Vantage / yfinance ──

def mock_income(rev_last, rev_yoy, gm, om, n=8):
    dates = pd.date_range(end="2024-12-31", periods=n, freq="QE")
    rows = []
    for i, d in enumerate(dates):
        rev = rev_last * ((1 + rev_yoy) ** ((i - (n - 1)) / 4))
        rows.append({
            "fiscalDateEnding": d,
            "totalRevenue": rev,
            "costOfRevenue": rev * (1 - gm),
            "grossProfit": rev * gm,
            "operatingIncome": rev * om,
        })
    return pd.DataFrame(rows)


def mock_balance(cash, long_term_debt):
    return pd.DataFrame([{
        "fiscalDateEnding": pd.Timestamp("2024-12-31"),
        "cashAndShortTermInvestments": cash,
        "cashAndCashEquivalentsAtCarryingValue": cash,
        "longTermDebt": long_term_debt,
    }])


def mock_cashflow(monthly_burn, n=4):
    dates = pd.date_range(end="2024-12-31", periods=n, freq="QE")
    return pd.DataFrame([
        {"fiscalDateEnding": d, "operatingCashflow": -monthly_burn * 3, "capitalExpenditures": 0.0}
        for d in dates
    ])


def mock_price(start_price, perf_12m, n=252, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end="2024-12-31", periods=n)
    target = start_price * (1 + perf_12m)
    step = (target - start_price) / (n - 1)
    prices = [start_price]
    for _ in range(1, n):
        prices.append(prices[-1] + step + rng.normal(0, start_price * 0.01))
    return pd.DataFrame({"Close": prices}, index=dates)


def mock_overview(ps, ev_sales, peg):
    return {
        "Symbol": "MOCK",
        "PriceToSalesRatioTTM": str(ps),
        "EVToRevenue": str(ev_sales),
        "PEGRatio": str(peg),
        "OperatingMarginTTM": "None",
        "RevenueTTM": "2000000000",
    }


def mock_insider(direction):
    """Format zgodny z yfinance Ticker.insider_transactions (kolumny Shares/Transaction)."""
    if direction == "none":
        return pd.DataFrame()
    rows = []
    if direction in ("buy", "mixed"):
        rows.append({"Shares": 50000, "Transaction": "Purchase"})
    if direction in ("sell", "mixed"):
        rows.append({"Shares": 30000, "Transaction": "Sale"})
    if direction == "sell":
        rows.append({"Shares": 200000, "Transaction": "Sale"})
    return pd.DataFrame(rows)


# (rev_yoy, gm, op_margin, cash, debt, monthly_burn, perf_12m, ps, ev_sales, peg, insider)
MOCK_UNIVERSE = {
    "STARGROW": (0.55, 0.72, 0.08, 800e6, 0,     10e6, 0.70, 12, 9,  1.2, "buy"),    # quality
    "MEDGRO":   (0.25, 0.55, 0.02, 200e6, 50e6,  8e6,  0.45, 14, 11, 2.0, "mixed"),  # watchlist/quality
    "SLOWCO":   (0.06, 0.40, 0.01, 100e6, 120e6, 5e6,  0.10, 6,  5,  4.0, "none"),   # reject (slow)
    "MOONSHOT": (0.45, 0.65, -0.30, 30e6, 10e6,  20e6, 2.80, 35, 28, 0.0, "sell"),   # reject (red lines)
    "DEBTBURG": (0.35, 0.50, -0.10, 120e6, 900e6, 12e6, 0.60, 10, 8, 0.0, "sell"),   # reject (debt/rsi)
}


def main():
    results = []
    for i, (ticker, p) in enumerate(MOCK_UNIVERSE.items()):
        rev_yoy, gm, om, cash, debt, burn, perf12, ps, evs, peg, insider = p
        data = {
            "income": mock_income(500e6, rev_yoy, gm, om),
            "balance": mock_balance(cash, debt),
            "cashflow": mock_cashflow(burn),
            "price": mock_price(100, perf12, seed=i),
            "overview": mock_overview(ps, evs, peg),
            "insider": mock_insider(insider),
        }
        metrics = met.compute_all(ticker, data)
        rules_eval = rl.evaluate_all(metrics)
        score = sc.compute_score(rules_eval)
        print(sc.format_report(ticker, metrics, rules_eval, score))
        results.append({"ticker": ticker, **metrics, **score})

    df = pd.DataFrame(results)
    order = {"quality": 0, "watchlist": 1, "reject": 2}
    df["_sort"] = df["label"].map(order).fillna(3)
    df = df.sort_values(["_sort", "pct"], ascending=[True, False]).drop(columns=["_sort"])
    df.to_csv("demo_results.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 64)
    print(" RANKING (demo)")
    print("=" * 64)
    cols = ["ticker", "label", "pct", "greens", "warnings", "reds",
            "revenue_growth_yoy", "gross_margin", "debt_to_revenue",
            "cash_runway_months", "perf_12m", "insider_net_ratio"]
    print(df[[c for c in cols if c in df.columns]].to_string(index=False))
    print("\n\u2705 Zapisano demo_results.csv")


if __name__ == "__main__":
    main()
