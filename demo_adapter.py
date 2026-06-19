#!/usr/bin/env python3
"""
demo_adapter.py
===============
Offline test adapterow data_client (bez sieci): sprawdza, ze surowe ramki w stylu
yfinance oraz dict-y w stylu .info / Finviz sa poprawnie normalizowane do kontraktu
konsumowanego przez metrics.compute_all(). Nie wymaga internetu ani kluczy.

Uruchom:  python demo_adapter.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_client as dc
import metrics as met
import rules as rl
import scoring as sc

DATES = pd.to_datetime([
    "2023-12-31", "2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"
])


def raw_income():
    # yfinance: wiersze = pozycje, kolumny = daty (tu przez .T)
    return pd.DataFrame({
        "Total Revenue":    [400e6, 430e6, 470e6, 520e6, 600e6],
        "Cost Of Revenue":  [120e6, 128e6, 138e6, 150e6, 168e6],
        "Gross Profit":     [280e6, 302e6, 332e6, 370e6, 432e6],
        "Operating Income": [20e6, 24e6, 30e6, 40e6, 55e6],
    }, index=DATES).T


def raw_balance():
    return pd.DataFrame({
        "Cash Cash Equivalents And Short Term Investments": [450e6, 470e6, 480e6, 490e6, 500e6],
        "Cash And Cash Equivalents": [200e6, 210e6, 220e6, 230e6, 240e6],
        "Long Term Debt": [100e6, 100e6, 100e6, 100e6, 100e6],
    }, index=DATES).T


def raw_cashflow():
    # capex w yfinance jest UJEMNY — adapter ma go zapisac jako dodatni
    return pd.DataFrame({
        "Operating Cash Flow": [50e6, 55e6, 60e6, 65e6, 70e6],
        "Capital Expenditure": [-10e6, -10e6, -12e6, -12e6, -15e6],
    }, index=DATES).T


def mock_price():
    pdates = pd.bdate_range(end="2024-12-31", periods=252)
    base = np.linspace(70, 100, 252)
    noise = np.random.default_rng(1).normal(0, 0.4, 252)
    return pd.DataFrame({"Close": base + noise}, index=pdates)


def main():
    info = {
        "priceToSalesTrailing12Months": 12.0,
        "enterpriseToRevenue": 9.0,
        "trailingPegRatio": 1.3,
        "trailingPE": 40.0,
        "operatingMargins": 0.09,
        "totalRevenue": 2.0e9,
        "revenueGrowth": 0.50,
    }
    finviz = {"P/S": "15.00", "PEG": "1.80", "Oper. Margin": "8.00%",
              "Sales Q/Q": "45.00%", "Sales": "2.10B"}

    # 1) Normalizacja sprawozdan
    inc = dc._normalize_income(raw_income())
    bal = dc._normalize_balance(raw_balance())
    cf = dc._normalize_cashflow(raw_cashflow())

    print("== Znormalizowane kolumny ==")
    print("income  :", list(inc.columns))
    print("balance :", list(bal.columns))
    print("cashflow:", list(cf.columns))
    assert {"totalRevenue", "grossProfit", "operatingIncome"} <= set(inc.columns)
    assert (cf["capitalExpenditures"] >= 0).all(), "capex powinien byc dodatni po normalizacji"

    # 2) Overview: .info (primary) + Finviz (fallback)
    ov_info = dc._overview_from_info(info)
    ov_fv = dc._overview_from_finviz(finviz)
    overview = dc._merge_overview(ov_info, ov_fv, "TESTCO")
    print("\n== Overview (info) ==\n", ov_info)
    print("== Overview (Finviz) ==\n", ov_fv)
    print("== Overview (merge: info wygrywa) ==\n", overview)
    assert overview["PriceToSalesRatioTTM"] == 12.0, "primary (.info) powinno wygrac z Finviz"
    assert abs(ov_fv["OperatingMarginTTM"] - 0.08) < 1e-9, "Finviz % -> ulamek"
    assert abs(ov_fv["RevenueTTM"] - 2.10e9) < 1.0, "Finviz 'B' -> liczba"

    # 3) Pelny pipeline na znormalizowanych danych
    data = {"income": inc, "balance": bal, "cashflow": cf,
            "overview": overview, "price": mock_price(), "insider": pd.DataFrame()}
    m = met.compute_all("TESTCO", data)
    r = rl.evaluate_all(m)
    s = sc.compute_score(r)
    print("\n" + sc.format_report("TESTCO", m, r, s))

    assert m["revenue_growth_yoy"] is not None and abs(m["revenue_growth_yoy"] - 0.5) < 1e-6
    assert m["gross_margin"] is not None
    assert m["debt_to_revenue"] is not None
    assert m["cash_runway_months"] == 999.0, "FCF dodatni => nieograniczone runway"
    print("\nADAPTER_OK")


if __name__ == "__main__":
    main()
