"""
rules.py
========
Mapowanie metryk na sygnaly: "green" / "warning" / "red".
Kazda regula zwraca (signal, reason) — reason to czytelne uzasadnienie.

Progi sa wiernym odwzorowaniem checklisty inwestycyjnej.
Brak danych => ("na", "N/A — brak danych"): regula opcjonalna, nie psuje scoringu.

HARD RED LINES (twarde veto, patrz scoring.py):
  - debt_to_revenue > 2x
  - cash_runway   < 6 miesiecy
  - perf_6m       > 200%
  - perf_12m      > 300%
  - rsi           > 75
  - pre_revenue   (brak sensownych przychodow)
"""
from __future__ import annotations

from typing import Optional, Tuple

Signal = str  # "green" | "warning" | "red" | "na"
RuleResult = Tuple[Signal, str]

NA: RuleResult = ("na", "N/A — brak danych")


def _is_na(val) -> bool:
    return val is None or (isinstance(val, float) and val != val)


# ──────────────────────── Revenue growth (Q3) ─────────────────────────────

def rule_revenue_growth(yoy: Optional[float]) -> RuleResult:
    if _is_na(yoy):
        return NA
    if yoy >= 0.30:
        return ("green", f"Revenue YoY {yoy:.1%} ≥ 30%")
    if yoy >= 0.10:
        return ("warning", f"Revenue YoY {yoy:.1%} (10–30%)")
    return ("red", f"Revenue YoY {yoy:.1%} < 10% lub spadek")


def rule_revenue_trend(slope: Optional[float]) -> RuleResult:
    if _is_na(slope):
        return NA
    if slope >= 0:
        return ("green", f"Trend przychodow rosnacy (slope={slope:+.3f})")
    return ("warning", f"Trend przychodow slabnacy (slope={slope:+.3f})")


# ──────────────────── Unit economics (Q4) ──────────────────────────────

def rule_gross_margin(gm: Optional[float]) -> RuleResult:
    if _is_na(gm):
        return NA
    if gm >= 0.50:
        return ("green", f"Gross margin {gm:.1%} ≥ 50%")
    if gm >= 0.30:
        return ("warning", f"Gross margin {gm:.1%} (30–50%)")
    return ("red", f"Gross margin {gm:.1%} < 30%")


def rule_operating_margin(om: Optional[float]) -> RuleResult:
    """Pomocnicza (opcjonalna) — operating margin sam w sobie."""
    if _is_na(om):
        return NA
    if om >= 0.0:
        return ("green", f"Operating margin {om:.1%} (dodatnia)")
    if om >= -0.15:
        return ("warning", f"Operating margin {om:.1%} (umiarkowana strata)")
    return ("red", f"Operating margin {om:.1%} (gleboka strata)")


def rule_gross_margin_trend(slope: Optional[float]) -> RuleResult:
    if _is_na(slope):
        return NA
    if slope >= 0:
        return ("green", f"Marza brutto rosnie (slope={slope:.4f})")
    return ("warning", f"Marza brutto spada (slope={slope:.4f})")


def rule_rule_of_40(r40: Optional[float]) -> RuleResult:
    if _is_na(r40):
        return NA
    if r40 >= 40:
        return ("green", f"Rule of 40: {r40:.1f} ≥ 40")
    if r40 >= 20:
        return ("warning", f"Rule of 40: {r40:.1f} (20–40)")
    return ("red", f"Rule of 40: {r40:.1f} < 20")


# ────────────────── Bilans & runway (Q6) — RED LINES ─────────────────────

def rule_debt_to_revenue(dtr: Optional[float]) -> RuleResult:
    if _is_na(dtr):
        return NA
    if dtr <= 0.5:
        return ("green", f"Dlug/Przychody {dtr:.2f}x ≤ 0.5x")
    if dtr <= 2.0:
        return ("warning", f"Dlug/Przychody {dtr:.2f}x (0.5–2x)")
    return ("red", f"Dlug/Przychody {dtr:.2f}x > 2x — RED LINE")


def rule_cash_runway(months: Optional[float]) -> RuleResult:
    if _is_na(months):
        return NA
    if months >= 999:
        return ("green", "Cash-flow positive — nieograniczone runway")
    if months >= 12:
        return ("green", f"Cash runway {months:.0f} mies. ≥ 12")
    if months >= 6:
        return ("warning", f"Cash runway {months:.0f} mies. (6–12)")
    return ("red", f"Cash runway {months:.0f} mies. < 6 — RED LINE")


# ───────────────────── Wycena (Q9) ─────────────────────────────────

def rule_valuation(ev_to_sales: Optional[float],
                   ps_ratio: Optional[float],
                   rev_growth: Optional[float]) -> RuleResult:
    """Wycena rozsadna wobec growth. Preferuje EV/Sales, fallback P/S.

    Przy wzroscie > 40% YoY akceptujemy wyzsza wycene (prog zielony 8x),
    w przeciwnym razie prog zielony to 6x. Ekstremum (>15x) => red.
    """
    metric = ev_to_sales if not _is_na(ev_to_sales) else ps_ratio
    label = "EV/Sales" if not _is_na(ev_to_sales) else "P/S"
    if _is_na(metric):
        return NA
    high_growth = (rev_growth or 0) >= 0.40
    green_thr = 8 if high_growth else 6
    red_thr = 15
    if metric <= green_thr:
        return ("green", f"{label} {metric:.1f}x — rozsadna wobec growth")
    if metric <= red_thr:
        return ("warning", f"{label} {metric:.1f}x — wycena premium")
    return ("red", f"{label} {metric:.1f}x > 15x — ekstremalna wycena")


def rule_peg(peg: Optional[float]) -> RuleResult:
    """Opcjonalna — PEG czesto niedostepny dla pre-profit growth."""
    if _is_na(peg) or peg <= 0:
        return NA
    if peg <= 1.5:
        return ("green", f"PEG {peg:.2f} ≤ 1.5")
    if peg <= 3.0:
        return ("warning", f"PEG {peg:.2f} (1.5–3)")
    return ("red", f"PEG {peg:.2f} > 3")


# ────────────────── Price action (Q9) — RED LINES ──────────────────────

def rule_perf_6m(perf: Optional[float]) -> RuleResult:
    if _is_na(perf):
        return NA
    if perf <= 1.00:
        return ("green", f"6M perf {perf:.1%} — brak parabolicznego rajdu")
    if perf <= 2.00:
        return ("warning", f"6M perf {perf:.1%} — silny rajd")
    return ("red", f"6M perf {perf:.1%} > 200% — RED LINE")


def rule_perf_12m(perf: Optional[float]) -> RuleResult:
    if _is_na(perf):
        return NA
    if perf <= 1.00:
        return ("green", f"12M perf {perf:.1%}")
    if perf <= 3.00:
        return ("warning", f"12M perf {perf:.1%} — szybki wzrost kursu")
    return ("red", f"12M perf {perf:.1%} > 300% — RED LINE")


def rule_rsi(rsi: Optional[float]) -> RuleResult:
    if _is_na(rsi):
        return NA
    if rsi <= 70:
        return ("green", f"RSI {rsi:.1f} ≤ 70")
    if rsi <= 75:
        return ("warning", f"RSI {rsi:.1f} (70–75) — wykupiony")
    return ("red", f"RSI {rsi:.1f} > 75 — RED LINE")


# ────────────────── Pre-revenue — RED LINE ───────────────────────────

def rule_pre_revenue(pre_rev: Optional[bool]) -> RuleResult:
    if pre_rev is None:
        return NA
    if pre_rev:
        return ("red", "Pre-revenue / brak sensownych przychodow — RED LINE")
    return ("green", "Firma raportuje sensowne przychody")


# ────────── Insider transactions (yfinance) — sygnal miekki, NIE hard red line ──────

def rule_insider(ratio: Optional[float]) -> RuleResult:
    if _is_na(ratio):
        return NA
    if ratio > 0:
        return ("green", f"Insiderzy kupuja netto (ratio={ratio:+.2f})")
    if ratio >= -0.75:
        return ("warning", f"Przewaga sprzedazy insiderow (ratio={ratio:+.2f})")
    return ("red", f"Silna wyprzedaz insiderow netto (ratio={ratio:+.2f})")


# ───────────────────── Dispatcher ──────────────────────────────────

def evaluate_all(m: dict) -> dict:
    """m = wyjscie metrics.compute_all(). Zwraca {rule_name: (signal, reason)}."""
    rev_growth = m.get("revenue_growth_yoy")
    return {
        "revenue_growth":     rule_revenue_growth(rev_growth),
        "revenue_trend":      rule_revenue_trend(m.get("revenue_trend_slope")),
        "gross_margin":       rule_gross_margin(m.get("gross_margin")),
        "gross_margin_trend": rule_gross_margin_trend(m.get("gross_margin_trend")),
        "operating_margin":   rule_operating_margin(m.get("operating_margin")),
        "rule_of_40":         rule_rule_of_40(m.get("rule_of_40")),
        "debt_to_revenue":    rule_debt_to_revenue(m.get("debt_to_revenue")),
        "cash_runway":        rule_cash_runway(m.get("cash_runway_months")),
        "valuation":          rule_valuation(m.get("ev_to_sales"), m.get("ps_ratio"), rev_growth),
        "peg":                rule_peg(m.get("peg_ratio")),
        "perf_6m":            rule_perf_6m(m.get("perf_6m")),
        "perf_12m":           rule_perf_12m(m.get("perf_12m")),
        "rsi":                rule_rsi(m.get("rsi_14")),
        "pre_revenue":        rule_pre_revenue(m.get("pre_revenue")),
        "insider":            rule_insider(m.get("insider_net_ratio")),
    }
