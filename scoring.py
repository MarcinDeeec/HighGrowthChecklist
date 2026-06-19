"""
scoring.py
==========
Wazony scoring + klasyfikacja koncowa: quality / watchlist / reject.

Najwieksze wagi (zgodnie z checklista): revenue growth, cash runway, debt.

Klasyfikacja:
  - quality   = duzo zielonych (>=8), 0 czerwonych, ZADNEJ hard red line
  - watchlist = wynik mieszany bez twardego faila (reds <= 2, brak hard red line)
  - reject    = >=3 czerwone ALBO jakakolwiek hard red line

Hard red line => ticker NIGDY nie moze byc quality (automatyczny veto).

Sygnaly "na" (brak danych) sa neutralne: nie licza sie do score ani do
mianownika — dzieki temu braki danych nie zanizaja sztucznie procentu.
"""
from __future__ import annotations

# Wagi regul — odzwierciedlaja waznosc z checklisty.
WEIGHTS = {
    "revenue_growth":     3,   # Q3 — najwazniejszy twardy wskaznik
    "revenue_trend":      2,   # Q3
    "gross_margin":       2,   # Q4
    "gross_margin_trend": 1,   # Q4
    "operating_margin":   1,   # Q4 (pomocnicza)
    "rule_of_40":         2,   # Q4
    "debt_to_revenue":    3,   # Q6 — RED LINE
    "cash_runway":        3,   # Q6 — RED LINE (przezycie)
    "valuation":          2,   # Q9
    "peg":                1,   # Q9 (opcjonalna)
    "perf_6m":            2,   # RED LINE
    "perf_12m":           1,   # RED LINE
    "rsi":                1,   # RED LINE
    "pre_revenue":        2,   # RED LINE
    "insider":            1,   # sygnal miekki z yfinance (opcjonalny)
}

SCORE_MAP = {"green": 2, "warning": 1, "red": 0}

# Reguly, ktorych czerwony sygnal = automatyczny REJECT (twarde veto).
HARD_RED_LINES = {
    "debt_to_revenue",
    "cash_runway",
    "perf_6m",
    "perf_12m",
    "rsi",
    "pre_revenue",
}


def compute_score(rules_eval: dict) -> dict:
    """Wejscie: {rule_name: (signal, reason)}.

    Zwraca dict ze score, pct, licznikami sygnalow i etykieta.
    """
    score = 0
    max_score = 0
    greens = warnings = reds = na = 0
    hard_red = False
    hard_red_hits = []

    for rule_name, (signal, _reason) in rules_eval.items():
        weight = WEIGHTS.get(rule_name, 1)

        if signal == "na":
            na += 1
            continue  # neutralne — poza scoringiem

        max_score += weight * 2
        score += SCORE_MAP.get(signal, 0) * weight

        if signal == "green":
            greens += 1
        elif signal == "warning":
            warnings += 1
        elif signal == "red":
            reds += 1
            if rule_name in HARD_RED_LINES:
                hard_red = True
                hard_red_hits.append(rule_name)

    pct = (score / max_score * 100) if max_score else 0.0

    # ── Klasyfikacja ──
    if hard_red or reds >= 3:
        label = "reject"
    elif greens >= 8 and reds == 0:
        label = "quality"
    elif reds <= 2:
        label = "watchlist"
    else:
        label = "reject"

    return {
        "score": score,
        "max_score": max_score,
        "pct": round(pct, 1),
        "greens": greens,
        "warnings": warnings,
        "reds": reds,
        "na": na,
        "hard_red": hard_red,
        "hard_red_lines": ",".join(hard_red_hits),
        "label": label,
    }


def label_badge(label: str) -> str:
    return {
        "quality":   "\U0001F7E2 QUALITY",
        "watchlist": "\U0001F7E1 WATCHLIST",
        "reject":    "\U0001F534 REJECT",
        "error":     "\u26A0\uFE0F  ERROR",
    }.get(label, label)


def format_report(ticker: str, metrics: dict, rules_eval: dict, score: dict) -> str:
    """Czytelny raport tekstowy dla jednego tickera (CLI)."""
    icons = {"green": "\u2705", "warning": "\u26A0\uFE0F", "red": "\U0001F534", "na": "\u2796"}
    bar = "=" * 64
    hard = "  \U0001F6D1 HARD RED LINE" if score.get("hard_red") else ""
    lines = [
        bar,
        f" {ticker} | {label_badge(score['label'])} | Score: {score['pct']}%{hard}",
        f" \u2705 {score['greens']}  \u26A0\uFE0F {score['warnings']}  "
        f"\U0001F534 {score['reds']}  \u2796 {score['na']}",
        bar,
    ]
    for rule, (signal, reason) in rules_eval.items():
        icon = icons.get(signal, "?")
        lines.append(f"  {icon} [{rule:18s}] {reason}")

    key_metrics = [
        ("Revenue YoY",  metrics.get("revenue_growth_yoy"), ".1%"),
        ("Gross margin", metrics.get("gross_margin"),       ".1%"),
        ("Op. margin",   metrics.get("operating_margin"),   ".1%"),
        ("Rule of 40",   metrics.get("rule_of_40"),         ".1f"),
        ("Debt/Rev",     metrics.get("debt_to_revenue"),    ".2f"),
        ("Runway (mo)",  metrics.get("cash_runway_months"), ".0f"),
        ("6M perf",      metrics.get("perf_6m"),            ".1%"),
        ("12M perf",     metrics.get("perf_12m"),           ".1%"),
        ("RSI-14",       metrics.get("rsi_14"),             ".1f"),
        ("EV/Sales",     metrics.get("ev_to_sales"),        ".1f"),
        ("P/S",          metrics.get("ps_ratio"),           ".1f"),
        ("PEG",          metrics.get("peg_ratio"),          ".2f"),
    ]
    lines.append("-" * 64)
    lines.append(" KEY METRICS")
    for name, val, fmt in key_metrics:
        if val is None:
            shown = "N/A"
        else:
            try:
                shown = format(val, fmt)
            except (ValueError, TypeError):
                shown = str(val)
        lines.append(f"  {name:14s}: {shown}")
    lines.append("")
    return "\n".join(lines)
