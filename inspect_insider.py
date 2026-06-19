#!/usr/bin/env python3
"""
inspect_insider.py
==================
Diagnostyka parsowania transakcji insiderow.

Tryb LIVE (wymaga internetu) — pokazuje, co dokladnie zwraca yfinance i jak
parser to interpretuje:
    python inspect_insider.py NVDA PLTR AAPL

Tryb OFFLINE (bez sieci) — testuje sam parser na danych w realnym ukladzie
kolumn yfinance (gdzie 'Transaction' bywa PUSTE, a typ siedzi w 'Text'):
    python inspect_insider.py --mock
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_client as dc
import metrics as met

# Realny uklad kolumn yfinance Ticker.insider_transactions:
_YF_COLS = ["Shares", "Value", "URL", "Text", "Insider", "Position",
            "Transaction", "Start Date", "Ownership"]


def _yf_row(shares, text, insider="", value=0):
    """Wiersz jak w yfinance: 'Transaction' PUSTE, opis w 'Text'."""
    return [shares, value, "", text, insider, "", "", "", ""]


def _mock_mixed() -> pd.DataFrame:
    rows = [
        _yf_row(10000, "Purchase at price 12.00 per share.", "Jane CEO"),
        _yf_row(5000, "Buy", "John CFO"),
        _yf_row(8000, "Sale at price 50.00 per share.", "Dir A"),
        _yf_row(2000, "Automatic Sale (10b5-1)", "Dir B"),
        _yf_row(3000, "Stock Award(Grant) at price 0.00 per share.", "VP C"),
        _yf_row(4000, "Stock Gift at price 0.00 per share.", "VP D"),
        _yf_row(1500, "Sale (disposition non open market)", "Dir E"),
        _yf_row(165514, "", "Holder X"),   # sam stan posiadania -> neutralne
    ]
    return pd.DataFrame(rows, columns=_YF_COLS)


def _mock_all_sells() -> pd.DataFrame:
    """Jak realne NVDA/AAPL: same sprzedaze + granty/gifty (neutralne)."""
    rows = [
        _yf_row(59509, "Stock Award(Grant) at price 0.00 per share.", "Gawel"),
        _yf_row(1000000, "Sale at price 217.66 - 222.38 per share.", "Stevens"),
        _yf_row(307500, "Stock Gift at price 0.00 per share.", "Stevens"),
        _yf_row(15500, "Sale at price 215.73 per share.", "Neal"),
        _yf_row(62650, "Sale at price 171.97 - 177.51 per share.", "Kress"),
    ]
    return pd.DataFrame(rows, columns=_YF_COLS)


def _report(ticker: str, df: pd.DataFrame) -> None:
    print("=" * 64)
    print(ticker)
    if df is None or getattr(df, "empty", True):
        print("  insider_transactions: PUSTE (zrodlo nic nie zwrocilo)")
        print("  insider_net_ratio   :", met.insider_net_ratio(df))
        return
    print("  kolumny:", list(df.columns))
    show = [c for c in ("Insider", "Transaction", "Text", "Shares", "Value") if c in df.columns]
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(df[show].head(12).to_string(index=False) if show else df.head(12).to_string())
    print("  insider_net_ratio   :", met.insider_net_ratio(df))


def _run_mock() -> int:
    mixed = _mock_mixed()
    _report("MOCK (mixed; 'Transaction' puste -> typ z 'Text')", mixed)
    r1 = met.insider_net_ratio(mixed)
    exp1 = (15000 - 11500) / (15000 + 11500)   # buys=Purchase+Buy; sells=Sale+AutoSale+disposition
    assert r1 is not None and abs(r1 - exp1) < 1e-9, (r1, exp1)
    print(f"  -> oczekiwano {exp1:+.4f} OK")

    sells = _mock_all_sells()
    _report("MOCK (same sprzedaze + granty/gifty)", sells)
    r2 = met.insider_net_ratio(sells)
    assert r2 is not None and abs(r2 - (-1.0)) < 1e-9, r2   # tylko sprzedaze -> -1.0
    print(f"  -> oczekiwano -1.0000 OK")

    print("\nINSIDER_PARSER_OK")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--mock" in argv:
        return _run_mock()
    tickers = [t.upper() for t in argv] or ["NVDA", "PLTR", "AAPL"]
    for t in tickers:
        try:
            df = dc.get_insider_transactions(t)
        except Exception as e:
            print("=" * 64)
            print(t, "-> blad pobierania:", e)
            continue
        _report(t, df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
