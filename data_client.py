"""
data_client.py — pobieranie danych z FMP i yfinance
Najpierw próbuje endpointów /stable, a jeśli dostanie błąd,
robi fallback do /api/v3.
"""
import os
import requests
import yfinance as yf
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

FMP_KEY = os.getenv("FMP_API_KEY", "demo")

FMP_BASE_STABLE = "https://financialmodelingprep.com/stable"
FMP_BASE_V3 = "https://financialmodelingprep.com/api/v3"


def _request_json(base: str, endpoint: str, params: dict | None = None):
    params = params or {}
    params = {"apikey": FMP_KEY, **params}
    r = requests.get(f"{base}/{endpoint}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def _fmp_dual(resource: str, symbol: str | None = None, params: dict | None = None):
    """
    Próbuje:
    1) /stable/{resource}?symbol=...
    2) /api/v3/{resource}/{symbol}?...
    3) /api/v3/{resource}?symbol=...
    """
    params = params or {}

    errors = []

    # 1) stable
    try:
        stable_params = dict(params)
        if symbol:
            stable_params["symbol"] = symbol
        return _request_json(FMP_BASE_STABLE, resource, stable_params)
    except Exception as e:
        errors.append(f"stable: {e}")

    # 2) v3 path style
    try:
        if symbol:
            return _request_json(FMP_BASE_V3, f"{resource}/{symbol}", params)
        return _request_json(FMP_BASE_V3, resource, params)
    except Exception as e:
        errors.append(f"v3-path: {e}")

    # 3) v3 query style
    try:
        v3_params = dict(params)
        if symbol:
            v3_params["symbol"] = symbol
        return _request_json(FMP_BASE_V3, resource, v3_params)
    except Exception as e:
        errors.append(f"v3-query: {e}")

    raise RuntimeError(" | ".join(errors))


def _to_df(data) -> pd.DataFrame:
    if not data or isinstance(data, dict):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date").reset_index(drop=True)
    return df


def get_income_statements(ticker: str, limit: int = 8) -> pd.DataFrame:
    data = _fmp_dual("income-statement", ticker, {"period": "quarter", "limit": limit})
    return _to_df(data)


def get_balance_sheet(ticker: str, limit: int = 4) -> pd.DataFrame:
    data = _fmp_dual("balance-sheet-statement", ticker, {"period": "quarter", "limit": limit})
    return _to_df(data)


def get_cash_flow(ticker: str, limit: int = 8) -> pd.DataFrame:
    data = _fmp_dual("cash-flow-statement", ticker, {"period": "quarter", "limit": limit})
    return _to_df(data)


def get_key_metrics(ticker: str, limit: int = 4) -> pd.DataFrame:
    data = _fmp_dual("key-metrics", ticker, {"period": "quarter", "limit": limit})
    return _to_df(data)


def get_ratios(ticker: str, limit: int = 4) -> pd.DataFrame:
    data = _fmp_dual("ratios", ticker, {"period": "quarter", "limit": limit})
    return _to_df(data)


def get_insider_trades(ticker: str, limit: int = 20) -> pd.DataFrame:
    data = _fmp_dual("insider-trading", ticker, {"limit": limit})
    return _to_df(data)


def get_price_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        return df
    except Exception:
        return pd.DataFrame()