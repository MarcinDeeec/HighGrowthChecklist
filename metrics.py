"""
metrics.py
==========
Czyste obliczenia: surowe DataFrame'y / overview  ->  liczby (lub None).

Kazda funkcja jest defensywna: brak danych => None (nigdy wyjatek).
Nazwy pol odpowiadaja Alpha Vantage:
  income:   totalRevenue, costOfRevenue, grossProfit, operatingIncome
  balance:  cashAndShortTermInvestments / cashAndCashEquivalentsAtCarryingValue, longTermDebt
  cashflow: operatingCashflow, capitalExpenditures
  overview: PriceToSalesRatioTTM, PEGRatio, EVToRevenue, OperatingMarginTTM, ...
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# Helpery
# ──────────────────────────────────────────────────────────────────────────────

def _num(val) -> Optional[float]:
    """Bezpieczna konwersja na float. 'None', '-', NaN, puste -> None."""
    if val is None:
        return None
    if isinstance(val, str):
        v = val.strip()
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
    if np.isnan(f):
        return None
    return f


def _cell(df: pd.DataFrame, idx: int, col: str) -> Optional[float]:
    """Wartosc z wiersza idx i kolumny col, odporna na braki kolumny / indeksu."""
    if df is None or df.empty or col not in df.columns:
        return None
    try:
        return _num(df.iloc[idx][col])
    except (IndexError, KeyError):
        return None


def _pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old)


def _ov(overview: dict, key: str) -> Optional[float]:
    if not overview:
        return None
    return _num(overview.get(key))


def _revenue(df: pd.DataFrame, idx: int) -> Optional[float]:
    """Przychod kwartalny; AV: totalRevenue (fallback: revenue)."""
    val = _cell(df, idx, "totalRevenue")
    if val is None:
        val = _cell(df, idx, "revenue")
    return val


# ──────────────────────────────────────────────────────────────────────────────
# 1. Revenue growth (YoY) + trend
# ──────────────────────────────────────────────────────────────────────────────

def revenue_growth_yoy(income_df: pd.DataFrame, overview: dict = None) -> Optional[float]:
    """YoY: najnowszy kwartal vs ten sam kwartal rok temu (iloc[-1] vs iloc[-5])."""
    if income_df is not None and len(income_df) >= 5:
        latest = _revenue(income_df, -1)
        year_ago = _revenue(income_df, -5)
        g = _pct_change(latest, year_ago)
        if g is not None:
            return g
    # Fallback: overview QuarterlyRevenueGrowthYOY (juz jako ulamek, np. 0.27)
    return _ov(overview or {}, "QuarterlyRevenueGrowthYOY")


def revenue_growth_trend(income_df: pd.DataFrame, n: int = 4) -> Optional[float]:
    """Trend przychodow. Znak ma znaczenie: >=0 rosnacy, <0 slabnacy.

    Dwa tryby (yfinance daje zwykle tylko ~4-5 kwartalow, wiec klasyczny
    slope YoY-growthow czesto sie nie liczyl -> N/A):
      - Tryb A (>=6 kwartalow): slope YoY-growthow z ostatnich n kwartalow
        (przyspieszenie wzrostu, odporne na sezonowosc) — preferowany.
      - Tryb B (4-5 kwartalow): slope POZIOMU przychodow QoQ z ostatnich
        min(n,len) kwartalow, znormalizowany przez sredni przychod
        (bezwymiarowy, porownywalny miedzy spolkami).
    """
    if income_df is None or len(income_df) < 2:
        return None
    # Tryb A: YoY-growthy (potrzeba >=6 kwartalow, by miec >=2 punkty YoY)
    yoy = []
    for i in range(4, len(income_df)):
        g = _pct_change(_revenue(income_df, i), _revenue(income_df, i - 4))
        if g is not None:
            yoy.append(g)
    if len(yoy) >= 2:
        yoy = yoy[-n:]
        x = np.arange(len(yoy))
        return float(np.polyfit(x, yoy, 1)[0])
    # Tryb B: trend poziomu przychodow (QoQ), znormalizowany srednia
    k = min(max(n, 4), len(income_df))
    revs = [_revenue(income_df, i) for i in range(-k, 0)]
    revs = [r for r in revs if r is not None]
    if len(revs) < 2:
        return None
    mean_rev = sum(revs) / len(revs)
    if not mean_rev:
        return None
    slope = float(np.polyfit(np.arange(len(revs)), revs, 1)[0])
    return slope / abs(mean_rev)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Marze
# ──────────────────────────────────────────────────────────────────────────────

def gross_margin(income_df: pd.DataFrame, overview: dict = None) -> Optional[float]:
    rev = _revenue(income_df, -1)
    gp = _cell(income_df, -1, "grossProfit")
    if rev and gp is not None:
        return gp / rev
    cogs = _cell(income_df, -1, "costOfRevenue")
    if rev and cogs is not None:
        return (rev - cogs) / rev
    # Overview nie ma czystego gross margin; ProfitMargin to net — nie podstawiamy.
    return None


def operating_margin(income_df: pd.DataFrame, overview: dict = None) -> Optional[float]:
    rev = _revenue(income_df, -1)
    oi = _cell(income_df, -1, "operatingIncome")
    if rev and oi is not None:
        return oi / rev
    return _ov(overview or {}, "OperatingMarginTTM")


def gross_margin_trend(income_df: pd.DataFrame, n: int = 4) -> Optional[float]:
    if income_df is None or len(income_df) < 2:
        return None
    margins = []
    start = max(0, len(income_df) - n)
    for i in range(start, len(income_df)):
        rev = _revenue(income_df, i)
        gp = _cell(income_df, i, "grossProfit")
        cogs = _cell(income_df, i, "costOfRevenue")
        if rev and gp is not None:
            margins.append(gp / rev)
        elif rev and cogs is not None:
            margins.append((rev - cogs) / rev)
    if len(margins) < 2:
        return None
    return float(np.polyfit(np.arange(len(margins)), margins, 1)[0])


# ──────────────────────────────────────────────────────────────────────────────
# 3. Rule of 40 = Revenue Growth % + Operating Margin %
# ──────────────────────────────────────────────────────────────────────────────

def rule_of_40(rev_growth_yoy: Optional[float], op_margin: Optional[float]) -> Optional[float]:
    if rev_growth_yoy is None or op_margin is None:
        return None
    return rev_growth_yoy * 100 + op_margin * 100


# ──────────────────────────────────────────────────────────────────────────────
# 4. Bilans: debt-to-revenue, cash runway
# ──────────────────────────────────────────────────────────────────────────────

def debt_to_revenue(balance_df: pd.DataFrame, income_df: pd.DataFrame) -> Optional[float]:
    """Long-term debt / TTM revenue (suma 4 ostatnich kwartalow)."""
    debt = _cell(balance_df, -1, "longTermDebt")
    if debt is None:
        debt = _cell(balance_df, -1, "longTermDebtNoncurrent")
    if income_df is None or income_df.empty or debt is None:
        return None
    revs = [_revenue(income_df, i) for i in range(-min(4, len(income_df)), 0)]
    revs = [r for r in revs if r is not None]
    ttm = sum(revs) if revs else None
    if not ttm:
        return None
    return debt / ttm


def cash_runway_months(balance_df: pd.DataFrame, cashflow_df: pd.DataFrame) -> Optional[float]:
    """Gotowka / sredni miesieczny burn. 999 = cash-flow positive (brak burnu).

    burn liczony z FCF = operatingCashflow - capitalExpenditures (AV nie daje FCF wprost).
    """
    cash = _cell(balance_df, -1, "cashAndShortTermInvestments")
    if cash is None:
        cash = _cell(balance_df, -1, "cashAndCashEquivalentsAtCarryingValue")
    if cash is None:
        return None
    if cashflow_df is None or cashflow_df.empty:
        return None

    fcfs = []
    for i in range(-min(4, len(cashflow_df)), 0):
        ocf = _cell(cashflow_df, i, "operatingCashflow")
        capex = _cell(cashflow_df, i, "capitalExpenditures")
        if ocf is None:
            continue
        # AV raportuje capex jako liczbe dodatnia (wydatek) -> odejmujemy.
        fcf = ocf - (capex or 0.0)
        fcfs.append(fcf)
    if not fcfs:
        return None

    burns = [f for f in fcfs if f < 0]
    if not burns:
        return 999.0  # generuje gotowke — nieograniczone runway
    avg_quarterly_burn = sum(burns) / len(burns)
    monthly_burn = abs(avg_quarterly_burn) / 3.0
    if monthly_burn == 0:
        return 999.0
    return cash / monthly_burn


# ──────────────────────────────────────────────────────────────────────────────
# 5. Price action (yfinance)
# ──────────────────────────────────────────────────────────────────────────────

def _close_series(price_df: pd.DataFrame) -> Optional[pd.Series]:
    if price_df is None or price_df.empty:
        return None
    if "Close" in price_df.columns:
        return price_df["Close"].dropna()
    if "Adj Close" in price_df.columns:
        return price_df["Adj Close"].dropna()
    return None


def price_performance(price_df: pd.DataFrame, months: int = 6) -> Optional[float]:
    s = _close_series(price_df)
    if s is None or len(s) < 5:
        return None
    try:
        cutoff = s.index[-1] - pd.DateOffset(months=months)
        window = s[s.index >= cutoff]
        if len(window) < 2:
            return None
        first, last = window.iloc[0], window.iloc[-1]
        if not first:
            return None
        return (last - first) / first
    except Exception:
        return None


def rsi_14(price_df: pd.DataFrame, period: int = 14) -> Optional[float]:
    s = _close_series(price_df)
    if s is None or len(s) < period + 1:
        return None
    try:
        delta = s.diff()
        gain = delta.clip(lower=0).ewm(com=period - 1, adjust=True).mean()
        loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=True).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        val = float(rsi.iloc[-1])
        return val if not np.isnan(val) else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# 6. Wycena (overview)
# ──────────────────────────────────────────────────────────────────────────────

def ps_ratio(overview: dict) -> Optional[float]:
    return _ov(overview or {}, "PriceToSalesRatioTTM")


def peg_ratio(overview: dict) -> Optional[float]:
    return _ov(overview or {}, "PEGRatio")


def ev_to_sales(overview: dict) -> Optional[float]:
    """EV/Sales. Alpha Vantage udostepnia EVToRevenue (to nasz odpowiednik)."""
    return _ov(overview or {}, "EVToRevenue")


def pe_ratio(overview: dict) -> Optional[float]:
    return _ov(overview or {}, "PERatio")


# ──────────────────────────────────────────────────────────────────────────────
# 7. Pre-revenue flag
# ──────────────────────────────────────────────────────────────────────────────

def is_pre_revenue(income_df: pd.DataFrame, overview: dict = None) -> Optional[bool]:
    """True jesli firma nie ma sensownych przychodow.

    Zwraca None gdy w ogole brak danych przychodowych (nie wiemy).
    Prog 1 mln USD TTM jako 'sensowne przychody'.
    """
    ttm = None
    if income_df is not None and not income_df.empty:
        revs = [_revenue(income_df, i) for i in range(-min(4, len(income_df)), 0)]
        revs = [r for r in revs if r is not None]
        if revs:
            ttm = sum(revs)
    if ttm is None:
        ttm = _ov(overview or {}, "RevenueTTM")
    if ttm is None:
        return None
    return ttm < 1_000_000


def insider_net_ratio(insider_df) -> Optional[float]:
    """Sygnal netto z transakcji insiderow w przedziale [-1, 1].

    +1 = wylacznie zakupy, -1 = wylacznie sprzedaz, 0 = rownowaga.
    None gdy brak danych lub brak transakcji typu kupno/sprzedaz.

    yfinance bywa niestabilny w nazwach kolumn, wiec dopasowujemy je
    elastycznie ('Transaction' lub 'Text' + 'Shares').
    """
    if insider_df is None or getattr(insider_df, "empty", True):
        return None
    try:
        cols = {str(c).strip().lower(): c for c in insider_df.columns}
    except Exception:
        return None
    # W yfinance typ transakcji bywa w 'Transaction' ALBO (czesto pusty
    # 'Transaction', a opis w) 'Text'. Laczymy wszystkie dostepne kolumny
    # opisowe, by nie przegapic typu niezaleznie od ukladu yfinance.
    text_cols = [cols[k] for k in ("transaction", "transaction type", "text", "title")
                 if k in cols]
    shares_col = cols.get("shares") or cols.get("share")
    if not text_cols or shares_col is None:
        return None

    BUY_KW = ("purchase", "buy", "bought", "acquisition", "acquire")
    SELL_KW = ("sale", "sell", "sold", "disposition", "dispose")

    buys = sells = 0.0
    for _, row in insider_df.iterrows():
        text = " ".join(str(row.get(c, "")) for c in text_cols).lower()
        shares = abs(_num(row.get(shares_col)) or 0.0)
        if shares == 0:
            continue
        # 'sale' przed 'buy'; reszta (award/grant/gift/option/holding) = neutralne
        if any(k in text for k in SELL_KW):
            sells += shares
        elif any(k in text for k in BUY_KW):
            buys += shares
    total = buys + sells
    if total == 0:
        return None
    return (buys - sells) / total


# ──────────────────────────────────────────────────────────────────────────────
# Wrapper: wszystkie metryki naraz
# ──────────────────────────────────────────────────────────────────────────────

def compute_all(ticker: str, data: dict) -> dict:
    """data = wynik data_client.fetch_all() lub analogiczny dict mock-ow."""
    income = data.get("income")
    balance = data.get("balance")
    cashflow = data.get("cashflow")
    overview = data.get("overview") or {}
    price = data.get("price")
    insider = data.get("insider")

    rev_growth = revenue_growth_yoy(income, overview)
    op_margin = operating_margin(income, overview)

    return {
        "ticker": ticker,
        "revenue_growth_yoy": rev_growth,
        "revenue_trend_slope": revenue_growth_trend(income),
        "gross_margin": gross_margin(income, overview),
        "gross_margin_trend": gross_margin_trend(income),
        "operating_margin": op_margin,
        "rule_of_40": rule_of_40(rev_growth, op_margin),
        "debt_to_revenue": debt_to_revenue(balance, income),
        "cash_runway_months": cash_runway_months(balance, cashflow),
        "perf_6m": price_performance(price, 6),
        "perf_12m": price_performance(price, 12),
        "rsi_14": rsi_14(price),
        "ps_ratio": ps_ratio(overview),
        "peg_ratio": peg_ratio(overview),
        "ev_to_sales": ev_to_sales(overview),
        "pe_ratio": pe_ratio(overview),
        "pre_revenue": is_pre_revenue(income, overview),
        "insider_net_ratio": insider_net_ratio(insider),
    }
