"""
data_client.py
==============
Warstwa pobierania danych (architektura: yfinance + Finviz).

Podzial pracy wg mocnych stron zrodel:
  - yfinance : glebokie dane per ticker -> kwartalne income/balance/cashflow,
               historia cen (RSI, performance) oraz insider transactions.
  - Finviz   : szybki snapshot fundamentow/wycen (fallback/uzupelnienie .info)
               oraz discovery calego rynku (zob. discovery.py).

Kontrakt danych jest TAKI SAM jak wczesniej (styl Alpha Vantage), zeby
metrics.py / rules.py / scoring.py nie wymagaly zmian:
  income:   DataFrame rosnaco po dacie; kolumny totalRevenue, costOfRevenue,
            grossProfit, operatingIncome
  balance:  DataFrame rosnaco; kolumny cashAndShortTermInvestments /
            cashAndCashEquivalentsAtCarryingValue, longTermDebt
  cashflow: DataFrame rosnaco; kolumny operatingCashflow, capitalExpenditures (dodatnie)
  overview: dict z kluczami w stylu Alpha Vantage (PriceToSalesRatioTTM, EVToRevenue,
            PEGRatio, PERatio, OperatingMarginTTM, RevenueTTM, QuarterlyRevenueGrowthYOY)
  price:    DataFrame z kolumna 'Close' i indeksem dat
  insider:  surowy DataFrame yfinance insider_transactions

Zasady:
  - Brak danych => pusty DataFrame / pusty dict (nigdy wyjatek 'w gore').
  - Wykryty rate-limit (np. Yahoo 'Too Many Requests') => RateLimitError,
    zeby main.py mogl wypisac komunikat i przejsc do kolejnego tickera.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except Exception:
    yf = None

try:
    from finvizfinance.quote import finvizfinance as _FinvizQuote
except Exception:
    _FinvizQuote = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# Lekki throttling miedzy tickerami. yfinance/Finviz nie maja twardego limitu
# dziennego jak Alpha Vantage, ale zbyt szybkie zapytania moga skutkowac
# chwilowym blokowaniem IP.
DEFAULT_PAUSE_SECONDS = float(os.getenv("SCREENER_PAUSE", "0.4"))
USE_FINVIZ = os.getenv("SCREENER_USE_FINVIZ", "1") not in {"0", "false", "False", ""}


class ScreenerDataError(RuntimeError):
    """Ogolny blad pobierania danych."""


class RateLimitError(ScreenerDataError):
    """Wykryto rate-limit (np. Yahoo 'Too Many Requests')."""


# Wstecznie kompatybilny alias (stare main.py lapalo AlphaVantageError).
AlphaVantageError = ScreenerDataError


def _is_rate_limit(exc: Exception) -> bool:
    txt = str(exc).lower()
    return any(k in txt for k in ("too many requests", "rate limit", "ratelimit", "429"))


# ---- helpery parsujace -------------------------------------------------------

def _num(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, str):
        v = val.strip().replace(",", "")
        if v in {"", "None", "-", "N/A", "nan"}:
            return None
        try:
            return float(v)
        except ValueError:
            return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if isinstance(f, float) and np.isnan(f):
        return None
    return f


def _finviz_pct(val) -> Optional[float]:
    """'12.34%' -> 0.1234 ; '-' -> None."""
    if val is None:
        return None
    s = str(val).strip()
    if s in {"", "-", "N/A"}:
        return None
    s = s.replace("%", "").replace(",", "")
    try:
        return float(s) / 100.0
    except ValueError:
        return None


_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _finviz_big(val) -> Optional[float]:
    """'1.50B' -> 1.5e9 ; '850.00M' -> 8.5e8 ; '-' -> None."""
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    if s in {"", "-", "N/A"}:
        return None
    mult = 1.0
    if s and s[-1].upper() in _SUFFIX:
        mult = _SUFFIX[s[-1].upper()]
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


# ---- normalizacja sprawozdan yfinance -> kontrakt AV-style -------------------

def _row_lookup(raw: pd.DataFrame, candidates) -> Optional[pd.Series]:
    """Znajduje wiersz (po etykiecie indeksu) pasujacy do jednego z candidates.

    Najpierw dokladne dopasowanie (case-insensitive), potem 'zawiera'.
    """
    if raw is None or getattr(raw, "empty", True):
        return None
    index_lower = {str(idx).strip().lower(): idx for idx in raw.index}
    for cand in candidates:
        key = cand.strip().lower()
        if key in index_lower:
            return raw.loc[index_lower[key]]
    for cand in candidates:
        key = cand.strip().lower()
        for low, orig in index_lower.items():
            if key in low:
                return raw.loc[orig]
    return None


_INCOME_MAP = {
    "totalRevenue": ["Total Revenue", "Operating Revenue"],
    "costOfRevenue": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "grossProfit": ["Gross Profit"],
    "operatingIncome": ["Operating Income", "Total Operating Income As Reported"],
}
_BALANCE_MAP = {
    "cashAndShortTermInvestments": [
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Short Term Investments",
    ],
    "cashAndCashEquivalentsAtCarryingValue": [
        "Cash And Cash Equivalents",
        "Cash Financial",
    ],
    "longTermDebt": [
        "Long Term Debt",
        "Long Term Debt And Capital Lease Obligation",
        "Total Debt",
    ],
}
_CASHFLOW_MAP = {
    "operatingCashflow": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capitalExpenditures": ["Capital Expenditure", "Capital Expenditure Reported"],
}


def _statement_to_df(raw: pd.DataFrame, field_map: dict, abs_fields=frozenset()) -> pd.DataFrame:
    """yfinance statement (wiersze=pozycje, kolumny=daty) -> AV-style DataFrame.

    Wynik: rosnaco po fiscalDateEnding; kolumny = klucze field_map + fiscalDateEnding.
    abs_fields: kolumny zapisywane jako wartosc bezwzgledna (np. capex w yfinance
    jest ujemny, a kontrakt oczekuje dodatniego jak w Alpha Vantage).
    """
    if raw is None or getattr(raw, "empty", True):
        return pd.DataFrame()
    periods = list(raw.columns)
    series_by_field = {av: _row_lookup(raw, cands) for av, cands in field_map.items()}
    rows = []
    for col in periods:
        row = {"fiscalDateEnding": pd.to_datetime(col, errors="coerce")}
        for av, ser in series_by_field.items():
            v = None
            if ser is not None:
                try:
                    v = _num(ser.get(col))
                except Exception:
                    v = None
            if v is not None and av in abs_fields:
                v = abs(v)
            row[av] = v
        rows.append(row)
    df = pd.DataFrame(rows)
    if "fiscalDateEnding" in df.columns:
        df = df.sort_values("fiscalDateEnding").reset_index(drop=True)
    return df


def _normalize_income(raw):
    return _statement_to_df(raw, _INCOME_MAP)


def _normalize_balance(raw):
    return _statement_to_df(raw, _BALANCE_MAP)


def _normalize_cashflow(raw):
    return _statement_to_df(raw, _CASHFLOW_MAP, abs_fields={"capitalExpenditures"})


# ---- overview: yfinance .info + Finviz fundament -----------------------------

def _overview_from_info(info: dict) -> dict:
    """yfinance Ticker.info -> overview w stylu Alpha Vantage (tylko niepuste pola)."""
    if not isinstance(info, dict) or not info:
        return {}
    out = {
        "PriceToSalesRatioTTM": info.get("priceToSalesTrailing12Months"),
        "EVToRevenue": info.get("enterpriseToRevenue"),
        "PEGRatio": info.get("trailingPegRatio", info.get("pegRatio")),
        "PERatio": info.get("trailingPE"),
        "OperatingMarginTTM": info.get("operatingMargins"),
        "RevenueTTM": info.get("totalRevenue"),
        "QuarterlyRevenueGrowthYOY": info.get("revenueGrowth"),
    }
    return {k: v for k, v in out.items() if v is not None}


def _overview_from_finviz(fund: dict) -> dict:
    """Finviz ticker_fundament() -> overview w stylu Alpha Vantage (fallback)."""
    if not isinstance(fund, dict) or not fund:
        return {}
    out = {
        "PriceToSalesRatioTTM": _num(fund.get("P/S")),
        "PEGRatio": _num(fund.get("PEG")),
        "PERatio": _num(fund.get("P/E")),
        "OperatingMarginTTM": _finviz_pct(fund.get("Oper. Margin")),
        "QuarterlyRevenueGrowthYOY": _finviz_pct(fund.get("Sales Q/Q")),
        "RevenueTTM": _finviz_big(fund.get("Sales")),
    }
    return {k: v for k, v in out.items() if v is not None}


def _merge_overview(primary: dict, fallback: dict, symbol: str) -> dict:
    """Laczy overview: primary (yfinance .info) wygrywa, Finviz uzupelnia braki."""
    merged = dict(fallback or {})
    merged.update({k: v for k, v in (primary or {}).items() if v is not None})
    if merged:
        merged.setdefault("Symbol", symbol)
    return merged


# ---- fetchery sieciowe -------------------------------------------------------

def _safe_attr(ticker_obj, name):
    try:
        return getattr(ticker_obj, name)
    except Exception:
        return None


def get_financials_yf(ticker: str):
    """(income, balance, cashflow, info) z yfinance — wszystko best-effort."""
    if yf is None:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}
    try:
        t = yf.Ticker(ticker)
        income = _normalize_income(_safe_attr(t, "quarterly_income_stmt"))
        balance = _normalize_balance(_safe_attr(t, "quarterly_balance_sheet"))
        cashflow = _normalize_cashflow(_safe_attr(t, "quarterly_cashflow"))
        try:
            info = t.info or {}
        except Exception:
            info = {}
        return income, balance, cashflow, info
    except Exception as e:
        if _is_rate_limit(e):
            raise RateLimitError(str(e)) from e
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}


def get_price_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Historyczne ceny dzienne z yfinance. Pusty DataFrame przy bledzie."""
    if yf is None:
        return pd.DataFrame()
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        if _is_rate_limit(e):
            raise RateLimitError(str(e)) from e
        return pd.DataFrame()


def get_insider_transactions(ticker: str) -> pd.DataFrame:
    """Transakcje insiderow z yfinance (Yahoo -> SEC Form 4). Pusty DF przy bledzie."""
    if yf is None:
        return pd.DataFrame()
    try:
        df = yf.Ticker(ticker).insider_transactions
        if df is None or df.empty:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()


def get_finviz_fundament(ticker: str) -> dict:
    """Snapshot fundamentow z Finviz (dict). {} przy bledzie / gdy wylaczone."""
    if _FinvizQuote is None or not USE_FINVIZ:
        return {}
    try:
        return _FinvizQuote(ticker).ticker_fundament() or {}
    except Exception:
        return {}


# ---- wrapper -----------------------------------------------------------------

def fetch_all(ticker: str) -> dict:
    """Komplet danych dla tickera w stabilnym kontrakcie (yfinance + Finviz)."""
    income, balance, cashflow, info = get_financials_yf(ticker)
    price = get_price_history(ticker, period="1y")
    insider = get_insider_transactions(ticker)

    ov_info = _overview_from_info(info)
    ov_finviz = _overview_from_finviz(get_finviz_fundament(ticker))
    overview = _merge_overview(primary=ov_info, fallback=ov_finviz, symbol=ticker)

    if DEFAULT_PAUSE_SECONDS:
        time.sleep(DEFAULT_PAUSE_SECONDS)

    return {
        "income": income,
        "balance": balance,
        "cashflow": cashflow,
        "overview": overview,
        "price": price,
        "insider": insider,
    }
