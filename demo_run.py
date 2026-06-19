#!/usr/bin/env python3
"""
demo_run.py — uruchomienie screenera na MOCK danych (bez FMP API key)
Pokazuje pełny pipeline: metrics -> rules -> scoring -> CSV export
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
import metrics as met
import rules as rl
import scoring as sc

# ── Mock data factory ─────────────────────────────────────────────────────────

def mock_income(rev_last, rev_growth_yoy, gm, om, n=8):
    """Generuje DataFrame income statements dla n kwartałów."""
    rows = []
    dates = pd.date_range(end="2024-12-31", periods=n, freq="QS")
    for i, d in enumerate(dates):
        rev = rev_last * ((1 + rev_growth_yoy) ** ((i - (n-1)) / 4))
        rows.append({
            "date": d,
            "revenue": rev,
            "costOfRevenue": rev * (1 - gm),
            "grossProfitRatio": gm,
            "operatingIncome": rev * om,
            "operatingIncomeRatio": om,
        })
    return pd.DataFrame(rows)

def mock_balance(cash, long_term_debt):
    return pd.DataFrame([{"date": pd.Timestamp("2024-12-31"),
                          "cashAndCashEquivalents": cash,
                          "longTermDebt": long_term_debt}])

def mock_cashflow(monthly_burn, n=4):
    rows = []
    dates = pd.date_range(end="2024-12-31", periods=n, freq="QS")
    for d in dates:
        rows.append({"date": d, "freeCashFlow": -monthly_burn * 3})
    return pd.DataFrame(rows)

def mock_price(start_price, perf_12m, n=252):
    dates = pd.bdate_range(end="2024-12-31", periods=n)
    prices = [start_price]
    target = start_price * (1 + perf_12m)
    step = (target - start_price) / (n - 1)
    for i in range(1, n):
        noise = np.random.normal(0, start_price * 0.015)
        prices.append(prices[-1] + step + noise)
    df = pd.DataFrame({"Close": prices}, index=dates)
    return df

def mock_metrics(ps, ev_sales):
    return pd.DataFrame([{"date": pd.Timestamp("2024-12-31"),
                          "priceToSalesRatio": ps, "evToSales": ev_sales}])

def mock_insider(sell_ratio):
    n = 20
    sells = int(n * sell_ratio)
    rows = []
    for i in range(n):
        rows.append({
            "transactionDate": (pd.Timestamp("2024-12-31") - pd.DateOffset(days=i*2)).strftime("%Y-%m-%d"),
            "transactionType": "S-Sale" if i < sells else "P-Purchase",
        })
    return pd.DataFrame(rows)


# ── Test cases — reprezentujące różne scenariusze z checklisty ────────────────

MOCK_UNIVERSE = {
    # Ticker: (rev_yoy, gm, op_margin, cash_M, debt_M, burn_M, perf_12m, ps, evs, insider_sell)
    "HYPEGRO": (0.65, 0.72, -0.05, 800e6, 0,      15e6,  0.80,  18, 14,  0.10),  # quality candidate
    "MEDGRO":  (0.25, 0.55, 0.05,  200e6, 50e6,   8e6,   0.45,  12,  9,  0.25),  # watchlist
    "SLOWCO":  (0.08, 0.40, 0.02,  100e6, 150e6,  5e6,   0.12,   6,  5,  0.30),  # reject (slow growth)
    "MOONSHOT":(0.45, 0.65, -0.20, 40e6,  10e6,   20e6,  2.50, 35, 28,  0.15),   # reject (red lines: perf, runway)
    "DEBTBURG":(0.35, 0.48, -0.10, 120e6, 800e6,  12e6,  0.60, 10,  8,  0.20),   # reject (debt > 2x)
    "STARGROW":(0.55, 0.68, 0.08,  600e6, 0,      10e6,  0.70, 15, 11,  0.05),   # quality
    "BORDERLN":(0.18, 0.52, 0.03,  90e6,  30e6,   8e6,   0.35,  9,  7,  0.40),   # watchlist
}

results = []
np.random.seed(42)

for ticker, params in MOCK_UNIVERSE.items():
    rev_yoy, gm, om, cash, debt, burn, perf12m, ps, evs, isr = params

    income_df   = mock_income(500e6, rev_yoy, gm, om)
    balance_df  = mock_balance(cash, debt)
    cashflow_df = mock_cashflow(burn)
    price_df    = mock_price(100, perf12m)
    metrics_df  = mock_metrics(ps, evs)
    insider_df  = mock_insider(isr)

    m = met.compute_all(ticker, income_df, balance_df, metrics_df,
                        cashflow_df, price_df, pd.DataFrame())
    # Manually patch insider & runway since mock_insider is separate
    m["insider_sell_ratio"] = isr

    rules_eval = rl.evaluate_all(m)
    score_result = sc.compute_score(rules_eval)

    print(sc.format_report(ticker, m, rules_eval, score_result))

    row = {"ticker": ticker, **m, **score_result}
    for rule_name, (signal, reason) in rules_eval.items():
        row[f"sig_{rule_name}"] = signal
    results.append(row)

df = pd.DataFrame(results)
order = {"quality": 0, "watchlist": 1, "reject": 2}
df["_sort"] = df["label"].map(order).fillna(3)
df = df.sort_values(["_sort", "pct"], ascending=[True, False]).drop(columns=["_sort"])

df.to_csv("demo_results.csv", index=False)
print("\n✅ Wyniki demo zapisane do: demo_results.csv")

# terminal ranking
print("\n" + "="*70)
print("RANKING")
print("="*70)
cols = ["ticker","label","pct","greens","reds",
        "revenue_growth_yoy","gross_margin","ev_to_sales","perf_6m","rsi_14"]
avail = [c for c in cols if c in df.columns]
print(df[avail].to_string(index=False))
