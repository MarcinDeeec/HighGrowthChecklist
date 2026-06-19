"""
metrics.py — obliczanie wszystkich metryk z checklisty
"""
import numpy as np
import pandas as pd
from typing import Optional

# ── helpers ────────────────────────────────────────────────────────────────────

def _safe(val, default=None):
    """Zwraca None jeśli val jest NaN/None, inaczej val."""
    if val is None:
        return default
    try:
        if np.isnan(float(val)):
            return default
    except (TypeError, ValueError):
        return default
    return val


def _pct_change(new, old) -> Optional[float]:
    if old and old != 0:
        return (new - old) / abs(old)
    return None

# ── 1. Revenue Growth ─────────────────────────────────────────────────────────

def revenue_growth_yoy(income_df: pd.DataFrame) -> Optional[float]:
    """YoY growth ostatniego kwartału vs. ten sam kwartał rok temu."""
    if len(income_df) < 5:
        return None
    latest = income_df.iloc[-1]["revenue"]
    year_ago = income_df.iloc[-5]["revenue"]
    return _pct_change(latest, year_ago)


def revenue_growth_trend(income_df: pd.DataFrame, n: int = 4) -> Optional[float]:
    """
    Trend przyspieszenia: slope korelacji Pearson z YoY growths
    ostatnich n kwartałów. Wartość > 0 = przyspieszający trend.
    """
    if len(income_df) < n + 4:
        return None
    growths = []
    for i in range(n):
        idx = -(i + 1)
        try:
            new = income_df.iloc[idx]["revenue"]
            old = income_df.iloc[idx - 4]["revenue"]
            g = _pct_change(new, old)
            if g is not None:
                growths.append(g)
        except IndexError:
            break
    if len(growths) < 2:
        return None
    x = np.arange(len(growths))
    slope = np.polyfit(x, growths[::-1], 1)[0]  # odwróć: chronologicznie
    return float(slope)


# ── 2. Gross / Operating Margin ───────────────────────────────────────────────

def gross_margin(income_df: pd.DataFrame) -> Optional[float]:
    """Gross margin ostatniego kwartału."""
    if income_df.empty:
        return None
    row = income_df.iloc[-1]
    rev = _safe(row.get("revenue"))
    cogs = _safe(row.get("costOfRevenue"))
    if rev and rev != 0 and cogs is not None:
        return (rev - cogs) / rev
    gm = _safe(row.get("grossProfitRatio"))
    return gm


def operating_margin(income_df: pd.DataFrame) -> Optional[float]:
    """Operating margin ostatniego kwartału."""
    if income_df.empty:
        return None
    row = income_df.iloc[-1]
    om = _safe(row.get("operatingIncomeRatio"))
    if om is not None:
        return om
    rev = _safe(row.get("revenue"))
    oi = _safe(row.get("operatingIncome"))
    if rev and rev != 0 and oi is not None:
        return oi / rev
    return None


def gross_margin_trend(income_df: pd.DataFrame, n: int = 4) -> Optional[float]:
    """Slope gross margin (rosnąca > 0)."""
    if len(income_df) < n:
        return None
    margins = []
    for row in income_df.tail(n).itertuples():
        rev = _safe(getattr(row, "revenue", None))
        cogs = _safe(getattr(row, "costOfRevenue", None))
        gm_ratio = _safe(getattr(row, "grossProfitRatio", None))
        if gm_ratio is not None:
            margins.append(gm_ratio)
        elif rev and cogs is not None and rev != 0:
            margins.append((rev - cogs) / rev)
    if len(margins) < 2:
        return None
    return float(np.polyfit(np.arange(len(margins)), margins, 1)[0])


# ── 3. Rule of 40 ─────────────────────────────────────────────────────────────

def rule_of_40(rev_growth_yoy: Optional[float], op_margin: Optional[float]) -> Optional[float]:
    """Rule of 40 = Revenue Growth % + Operating Margin %"""
    if rev_growth_yoy is None or op_margin is None:
        return None
    return rev_growth_yoy * 100 + op_margin * 100


# ── 4. Debt & Cash Runway ─────────────────────────────────────────────────────

def debt_to_revenue(balance_df: pd.DataFrame, income_df: pd.DataFrame) -> Optional[float]:
    """Long-term debt / TTM revenue (red flag jeśli >2x)."""
    if balance_df.empty or income_df.empty:
        return None
    debt = _safe(balance_df.iloc[-1].get("longTermDebt"))
    ttm_rev = income_df.tail(4)["revenue"].sum()
    if ttm_rev and ttm_rev != 0 and debt is not None:
        return debt / ttm_rev
    return None


def cash_runway_months(balance_df: pd.DataFrame, cashflow_df: pd.DataFrame) -> Optional[float]:
    """
    Gotówka / avg monthly burn = miesięcy runway.
    burn = abs(avg kwartalny free cash flow jeśli ujemny)
    """
    if balance_df.empty or cashflow_df.empty:
        return None
    cash = _safe(balance_df.iloc[-1].get("cashAndCashEquivalents"))
    if cash is None:
        return None
    fcf_q = cashflow_df.tail(4).get("freeCashFlow", pd.Series(dtype=float))
    if fcf_q.empty:
        return None
    avg_burn_q = fcf_q[fcf_q < 0].mean()
    if pd.isna(avg_burn_q) or avg_burn_q == 0:
        return 999.0  # cash-flow positive
    monthly_burn = abs(avg_burn_q) / 3
    return cash / monthly_burn if monthly_burn else None


# ── 5. Price Action ───────────────────────────────────────────────────────────

def price_performance(price_df: pd.DataFrame, months: int = 6) -> Optional[float]:
    """Zwrot procentowy w ostatnich `months` miesiącach."""
    if price_df.empty:
        return None
    try:
        col = "Close" if "Close" in price_df.columns else price_df.columns[3]
        cutoff = price_df.index[-1] - pd.DateOffset(months=months)
        recent = price_df[price_df.index >= cutoff]
        if len(recent) < 5:
            return None
        return (recent[col].iloc[-1] - recent[col].iloc[0]) / recent[col].iloc[0]
    except Exception:
        return None


def rsi(price_df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """RSI (14-dniowy) na ostatniej świecy."""
    if price_df.empty or len(price_df) < period + 1:
        return None
    try:
        col = "Close" if "Close" in price_df.columns else price_df.columns[3]
        delta = price_df[col].diff()
        gain = delta.clip(lower=0).ewm(com=period - 1, adjust=True).mean()
        loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=True).mean()
        rs = gain / loss
        rsi_val = 100 - (100 / (1 + rs))
        return float(rsi_val.iloc[-1])
    except Exception:
        return None


# ── 6. Valuation ──────────────────────────────────────────────────────────────

def ps_ratio(metrics_df: pd.DataFrame) -> Optional[float]:
    if metrics_df.empty:
        return None
    return _safe(metrics_df.iloc[-1].get("priceToSalesRatio"))


def ev_to_sales(metrics_df: pd.DataFrame) -> Optional[float]:
    if metrics_df.empty:
        return None
    return _safe(metrics_df.iloc[-1].get("evToSales")) or _safe(metrics_df.iloc[-1].get("enterpriseValueOverEBITDA"))


def peg_ratio(metrics_df: pd.DataFrame) -> Optional[float]:
    if metrics_df.empty:
        return None
    return _safe(metrics_df.iloc[-1].get("priceEarningsToGrowthRatio"))


# ── 7. Insider Selling Pressure ───────────────────────────────────────────────

def insider_sell_ratio(insider_df: pd.DataFrame) -> Optional[float]:
    """Stosunek sprzedanych do wszystkich transakcji (90 dni)."""
    if insider_df.empty:
        return None
    try:
        recent = insider_df.copy()
        if "transactionDate" in recent.columns:
            recent["transactionDate"] = pd.to_datetime(recent["transactionDate"], errors="coerce")
            cutoff = pd.Timestamp.today() - pd.DateOffset(days=90)
            recent = recent[recent["transactionDate"] >= cutoff]
        sells = recent[recent.get("transactionType", pd.Series()).str.contains("S-Sale|Sell", na=False)]
        total = len(recent)
        return len(sells) / total if total > 0 else 0.0
    except Exception:
        return None


# ── wrapper: wszystkie metryki naraz ─────────────────────────────────────────

def compute_all(ticker: str, income_df, balance_df, metrics_df,
                cashflow_df, price_df, insider_df) -> dict:
    rev_growth = revenue_growth_yoy(income_df)
    op_margin = operating_margin(income_df)
    return {
        "ticker": ticker,
        "revenue_growth_yoy": rev_growth,
        "revenue_trend_slope": revenue_growth_trend(income_df),
        "gross_margin": gross_margin(income_df),
        "gross_margin_trend": gross_margin_trend(income_df),
        "operating_margin": op_margin,
        "rule_of_40": rule_of_40(rev_growth, op_margin),
        "debt_to_revenue": debt_to_revenue(balance_df, income_df),
        "cash_runway_months": cash_runway_months(balance_df, cashflow_df),
        "perf_6m": price_performance(price_df, 6),
        "perf_12m": price_performance(price_df, 12),
        "rsi_14": rsi(price_df),
        "ps_ratio": ps_ratio(metrics_df),
        "ev_to_sales": ev_to_sales(metrics_df),
        "peg_ratio": peg_ratio(metrics_df),
        "insider_sell_ratio": insider_sell_ratio(insider_df),
    }
