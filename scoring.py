"""
scoring.py — końcowy scoring i klasyfikacja
quality  : ≥ 8 zielonych + 0 czerwonych
watchlist: 5-7 zielonych + max 2 czerwone (i żadna nie z Q6/Q10 proxy)
reject   : ≥ 3 czerwone ALBO czerwona w debt/runway/perf_6m/rsi
"""


# wagi reguł — odzwierciedlają ważność z checklisty
WEIGHTS = {
    "revenue_growth":     3,   # Q3 — najważniejszy twardy wskaźnik
    "revenue_trend":      2,   # Q3 — trend
    "gross_margin":       2,   # Q4
    "gross_margin_trend": 1,   # Q4
    "rule_of_40":         2,   # Q4
    "debt_to_revenue":    2,   # Q6 — Red Line proxy
    "cash_runway":        3,   # Q6/Q10 — przeżycie (Red Line)
    "ev_to_sales":        2,   # Q9
    "ps_ratio":           1,   # Q9
    "perf_6m":            2,   # Red Line #1
    "perf_12m":           1,   # Red Line #1
    "rsi":                1,   # Red Line #6
    "insider_selling":    1,   # Red Line #3
}

SCORE_MAP = {"green": 2, "warning": 1, "red": 0}

# Reguły, których czerwona oznacza automatyczny REJECT (Red Lines z checklisty)
HARD_RED_LINES = {"debt_to_revenue", "cash_runway", "perf_6m", "rsi"}


def compute_score(rules_eval: dict) -> dict:
    """
    Wejście: {rule_name: (signal, reason)}
    Wyjście: {score, max_score, pct, greens, warnings, reds, hard_red, label}
    """
    score = 0
    max_score = 0
    greens = warnings = reds = 0
    hard_red = False

    for rule_name, (signal, _) in rules_eval.items():
        if signal == "warning" and rule_name not in WEIGHTS:
            continue  # ignoruj nieznane reguły
        w = WEIGHTS.get(rule_name, 1)
        max_score += w * 2
        score += SCORE_MAP[signal] * w

        if signal == "green":
            greens += 1
        elif signal == "warning":
            warnings += 1
        else:
            reds += 1
            if rule_name in HARD_RED_LINES:
                hard_red = True

    pct = score / max_score if max_score else 0

    # klasyfikacja
    if hard_red or reds >= 3:
        label = "reject"
    elif greens >= 8 and reds == 0:
        label = "quality"
    elif greens >= 5 and reds <= 2:
        label = "watchlist"
    elif reds >= 2:
        label = "reject"
    else:
        label = "watchlist"

    return {
        "score": score,
        "max_score": max_score,
        "pct": round(pct * 100, 1),
        "greens": greens,
        "warnings": warnings,
        "reds": reds,
        "hard_red": hard_red,
        "label": label,
    }


def label_emoji(label: str) -> str:
    return {"quality": "🟢 QUALITY", "watchlist": "🟡 WATCHLIST", "reject": "🔴 REJECT"}.get(label, label)


def format_report(ticker: str, metrics: dict, rules_eval: dict, score_result: dict) -> str:
    lines = [
        f"{'='*60}",
        f"  {ticker}  |  {label_emoji(score_result['label'])}  |  Score: {score_result['pct']}%",
        f"  ✅ {score_result['greens']}  ⚠️ {score_result['warnings']}  🔴 {score_result['reds']}  {'🔴 HARD RED LINE' if score_result['hard_red'] else ''}",
        f"{'='*60}",
    ]
    for rule, (signal, reason) in rules_eval.items():
        icon = {"green": "✅", "warning": "⚠️", "red": "🔴"}[signal]
        lines.append(f"  {icon} [{rule:20s}] {reason}")

    key_metrics = [
        ("Revenue YoY",       metrics.get("revenue_growth_yoy"),   ".1%"),
        ("Gross Margin",      metrics.get("gross_margin"),          ".1%"),
        ("Op. Margin",        metrics.get("operating_margin"),      ".1%"),
        ("Rule of 40",        metrics.get("rule_of_40"),            ".1f"),
        ("Debt/Rev",          metrics.get("debt_to_revenue"),       ".2f"),
        ("Runway (mo.)",      metrics.get("cash_runway_months"),    ".0f"),
        ("6M Perf",           metrics.get("perf_6m"),               ".1%"),
        ("12M Perf",          metrics.get("perf_12m"),              ".1%"),
        ("RSI-14",            metrics.get("rsi_14"),                ".1f"),
        ("EV/Sales",          metrics.get("ev_to_sales"),           ".1f"),
        ("P/S",               metrics.get("ps_ratio"),              ".1f"),
    ]
    lines.append(f"{'─'*60}")
    lines.append("  KEY METRICS")
    for name, val, fmt in key_metrics:
        if val is not None:
            try:
                fval = format(val, fmt)
            except (ValueError, TypeError):
                fval = str(val)
            lines.append(f"  {name:20s}: {fval}")
    lines.append("")
    return "\n".join(lines)
