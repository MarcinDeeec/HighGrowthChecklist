"""
rules.py — mapowanie metryk na ✅ / ⚠️ / 🔴
Każda reguła zwraca (signal, reason)
signal: "green" | "warning" | "red"
"""
from typing import Optional, Tuple

Signal = str  # "green" | "warning" | "red"
RuleResult = Tuple[Signal, str]

NA = ("warning", "N/A — brak danych")


def _na(val) -> bool:
    return val is None or (isinstance(val, float) and val != val)


# ────────────────────────────────────────────────────────────────────────────────
# Checklist Q3 — Revenue Growth
# ────────────────────────────────────────────────────────────────────────────────

def rule_revenue_growth(yoy: Optional[float]) -> RuleResult:
    if _na(yoy):
        return NA
    if yoy >= 0.30:
        return ("green", f"Revenue YoY: {yoy:.1%} ≥ 30%")
    if yoy >= 0.10:
        return ("warning", f"Revenue YoY: {yoy:.1%} — umiarkowany wzrost")
    return ("red", f"Revenue YoY: {yoy:.1%} < 10% (lub spadek)")


def rule_revenue_trend(slope: Optional[float]) -> RuleResult:
    if _na(slope):
        return NA
    if slope >= 0:
        return ("green", f"Trend wzrostu przychodów: przyspieszający (slope={slope:.3f})")
    return ("warning", f"Trend wzrostu przychodów: zwalniający (slope={slope:.3f})")


# ────────────────────────────────────────────────────────────────────────────────
# Checklist Q4 — Gross Margin & Rule of 40
# ────────────────────────────────────────────────────────────────────────────────

def rule_gross_margin(gm: Optional[float]) -> RuleResult:
    if _na(gm):
        return NA
    if gm >= 0.50:
        return ("green", f"Gross margin: {gm:.1%} ≥ 50%")
    if gm >= 0.30:
        return ("warning", f"Gross margin: {gm:.1%} — poniżej ideału, ale akceptowalne")
    return ("red", f"Gross margin: {gm:.1%} < 30% — słabe unit economics")


def rule_gross_margin_trend(slope: Optional[float]) -> RuleResult:
    if _na(slope):
        return NA
    if slope >= 0:
        return ("green", f"Marża brutto rośnie (slope={slope:.4f})")
    return ("warning", f"Marża brutto spada (slope={slope:.4f})")


def rule_rule_of_40(r40: Optional[float]) -> RuleResult:
    if _na(r40):
        return NA
    if r40 >= 40:
        return ("green", f"Rule of 40: {r40:.1f} ≥ 40")
    if r40 >= 20:
        return ("warning", f"Rule of 40: {r40:.1f} — w okolicach granicy")
    return ("red", f"Rule of 40: {r40:.1f} < 20 — słaba efektywność")


# ────────────────────────────────────────────────────────────────────────────────
# Checklist Q6 — Bilans & Runway
# ────────────────────────────────────────────────────────────────────────────────

def rule_debt_to_revenue(dtr: Optional[float]) -> RuleResult:
    if _na(dtr):
        return NA
    if dtr <= 0.5:
        return ("green", f"Dług/Przychody: {dtr:.2f}x — zdrowy bilans")
    if dtr <= 2.0:
        return ("warning", f"Dług/Przychody: {dtr:.2f}x — umiarkowane zadłużenie")
    return ("red", f"Dług/Przychody: {dtr:.2f}x > 2x — RED LINE: dług przekracza 2x przychody")


def rule_cash_runway(months: Optional[float]) -> RuleResult:
    if _na(months):
        return NA
    if months >= 999:
        return ("green", "Cash-flow positive — nieograniczone runway")
    if months >= 12:
        return ("green", f"Cash runway: {months:.0f} miesięcy ≥ 12")
    if months >= 6:
        return ("warning", f"Cash runway: {months:.0f} miesięcy — obserwuj")
    return ("red", f"Cash runway: {months:.0f} miesięcy < 6 — RED LINE: ryzyko przeżycia")


# ────────────────────────────────────────────────────────────────────────────────
# Checklist Q9 — Wycena & Price Action (RED LINES)
# ────────────────────────────────────────────────────────────────────────────────

def rule_ev_to_sales(evs: Optional[float], rev_growth: Optional[float]) -> RuleResult:
    if _na(evs):
        return NA
    # Jeśli wzrost > 40% akceptujemy wyższe wyceny
    threshold_green = 8 if (rev_growth or 0) >= 0.40 else 6
    threshold_red = 15
    if evs <= threshold_green:
        return ("green", f"EV/Sales: {evs:.1f}x — rozsądna wycena")
    if evs <= threshold_red:
        return ("warning", f"EV/Sales: {evs:.1f}x — wycena premium")
    return ("red", f"EV/Sales: {evs:.1f}x > 15x — RED LINE: ekstremalna wycena bez zysku")


def rule_ps_ratio(ps: Optional[float]) -> RuleResult:
    if _na(ps):
        return NA
    if ps <= 8:
        return ("green", f"P/S: {ps:.1f}x — rozsądny")
    if ps <= 20:
        return ("warning", f"P/S: {ps:.1f}x — podwyższony")
    return ("red", f"P/S: {ps:.1f}x > 20x — bardzo drogo")


def rule_perf_6m(perf: Optional[float]) -> RuleResult:
    """Red Line #1: >200% w 6 miesięcy."""
    if _na(perf):
        return NA
    if perf <= 1.00:
        return ("green", f"6M performance: {perf:.1%} — brak parabolicznego rajdu")
    if perf <= 2.00:
        return ("warning", f"6M performance: {perf:.1%} — silny rajd, uważaj")
    return ("red", f"6M performance: {perf:.1%} > 200% — RED LINE: paraboliczny rajd")


def rule_perf_12m(perf: Optional[float]) -> RuleResult:
    if _na(perf):
        return NA
    if perf <= 1.00:
        return ("green", f"12M performance: {perf:.1%}")
    if perf <= 3.00:
        return ("warning", f"12M performance: {perf:.1%} — szybki wzrost kursu")
    return ("red", f"12M performance: {perf:.1%} > 300% — RED LINE: ekstremalne przebicie")


def rule_rsi(rsi_val: Optional[float]) -> RuleResult:
    """Red Line #6: RSI > 75."""
    if _na(rsi_val):
        return NA
    if rsi_val <= 70:
        return ("green", f"RSI: {rsi_val:.1f} ≤ 70")
    if rsi_val <= 75:
        return ("warning", f"RSI: {rsi_val:.1f} — lekko wykupiony")
    return ("red", f"RSI: {rsi_val:.1f} > 75 — RED LINE: ekstremalnie wykupiony")


# ────────────────────────────────────────────────────────────────────────────────
# Insider Selling (Red Line #3)
# ────────────────────────────────────────────────────────────────────────────────

def rule_insider_selling(sell_ratio: Optional[float]) -> RuleResult:
    if _na(sell_ratio):
        return NA
    if sell_ratio <= 0.30:
        return ("green", f"Insider sell ratio: {sell_ratio:.0%} — brak alarmu")
    if sell_ratio <= 0.60:
        return ("warning", f"Insider sell ratio: {sell_ratio:.0%} — umiarkowana sprzedaż")
    return ("red", f"Insider sell ratio: {sell_ratio:.0%} > 60% — RED LINE: masowa sprzedaż insiderów")


# ────────────────────────────────────────────────────────────────────────────────
# Dispatcher — wszystkie reguły naraz
# ────────────────────────────────────────────────────────────────────────────────

def evaluate_all(m: dict) -> dict:
    """
    m = output z metrics.compute_all()
    Zwraca dict {rule_name: (signal, reason)}
    """
    rev_growth = m.get("revenue_growth_yoy")
    return {
        "revenue_growth":    rule_revenue_growth(rev_growth),
        "revenue_trend":     rule_revenue_trend(m.get("revenue_trend_slope")),
        "gross_margin":      rule_gross_margin(m.get("gross_margin")),
        "gross_margin_trend":rule_gross_margin_trend(m.get("gross_margin_trend")),
        "rule_of_40":        rule_rule_of_40(m.get("rule_of_40")),
        "debt_to_revenue":   rule_debt_to_revenue(m.get("debt_to_revenue")),
        "cash_runway":       rule_cash_runway(m.get("cash_runway_months")),
        "ev_to_sales":       rule_ev_to_sales(m.get("ev_to_sales"), rev_growth),
        "ps_ratio":          rule_ps_ratio(m.get("ps_ratio")),
        "perf_6m":           rule_perf_6m(m.get("perf_6m")),
        "perf_12m":          rule_perf_12m(m.get("perf_12m")),
        "rsi":               rule_rsi(m.get("rsi_14")),
        "insider_selling":   rule_insider_selling(m.get("insider_sell_ratio")),
    }
