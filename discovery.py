"""
discovery.py
============
Warstwa discovery (skanowanie rynku) -> lista tickerow kandydatow.

Glowne zrodlo: Finviz (finvizfinance) — screener calego rynku US bez klucza API.
Fallback: yfinance predefiniowany screen (gdy finvizfinance niedostepne).

UWAGA: etykiety filtrow Finviz pochodza wprost z UI Finviz i moga sie zmieniac
w czasie. Jesli ktorys filtr przestanie dzialac, zaktualizuj slownik PRESETS
lub podaj wlasny filters_dict. Pomocne: available_filters().
"""
from __future__ import annotations

from typing import Optional

try:
    from finvizfinance.screener.overview import Overview as _Overview
except Exception:
    _Overview = None

try:
    import yfinance as yf
except Exception:
    yf = None


# Gotowe presety filtrow Finviz (czytelne etykiety z UI Finviz).
PRESETS = {
    "growth": {
        "Country": "USA",
        "Market Cap.": "+Small (over $300mln)",
        "Sales growthqtr over qtr": "Over 25%",
        "Average Volume": "Over 500K",
    },
    "high_growth": {
        "Country": "USA",
        "Market Cap.": "+Small (over $300mln)",
        "Sales growthqtr over qtr": "Over 25%",
        "EPS growthqtr over qtr": "Over 25%",
        "Average Volume": "Over 500K",
    },
    "hypergrowth": {
        "Country": "USA",
        "Market Cap.": "+Mid (over $2bln)",
        "Sales growthqtr over qtr": "Over 50%",
        "Average Volume": "Over 1M",
    },
}


def list_presets():
    return sorted(PRESETS.keys())


def available_filters():
    """Zwraca dostepne filtry Finviz (do budowy wlasnego filters_dict)."""
    if _Overview is None:
        return {}
    fo = _Overview()
    for meth in ("get_filters", "getFilters"):
        fn = getattr(fo, meth, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return {}


def _discover_finviz(filters_dict, signal, order, ascend, limit):
    fo = _Overview()
    fo.set_filter(filters_dict=filters_dict or {}, signal=signal or "")
    df = None
    try:
        df = fo.screener_view(order=order or "", limit=(limit or -1),
                              ascend=ascend, verbose=0)
    except TypeError:
        # starsze/inne wersje finvizfinance moga miec inna sygnature
        try:
            df = fo.screener_view()
        except Exception:
            return []
    except Exception:
        return []
    if df is None or len(df) == 0:
        return []
    col = "Ticker" if "Ticker" in df.columns else df.columns[0]
    tickers = [str(t).strip().upper() for t in df[col].tolist() if str(t).strip()]
    if limit:
        tickers = tickers[:limit]
    return tickers


def _discover_yf(limit):
    """Fallback: predefiniowany screen Yahoo (gdy Finviz niedostepny)."""
    if yf is None:
        return []
    try:
        res = yf.screen("growth_technology_stocks")
        quotes = (res or {}).get("quotes", []) if isinstance(res, dict) else []
        tickers = [q.get("symbol") for q in quotes if isinstance(q, dict) and q.get("symbol")]
        tickers = [t.upper() for t in tickers]
        if limit:
            tickers = tickers[:limit]
        return tickers
    except Exception:
        return []


def discover(preset: Optional[str] = None, filters: Optional[dict] = None,
             signal: Optional[str] = None, order: Optional[str] = None,
             ascend: bool = False, limit: Optional[int] = None):
    """Zwraca liste tickerow kandydatow.

    preset  : nazwa z PRESETS (np. 'growth'); ignorowane, gdy podasz 'filters'.
    filters : wlasny filters_dict Finviz (nadpisuje preset).
    signal  : sygnal Finviz (np. 'Top Gainers') — opcjonalny.
    order   : pole sortowania Finviz (np. 'Sales growthqtr over qtr').
    ascend  : kierunek sortowania.
    limit   : maksymalna liczba tickerow.
    """
    filters_dict = filters if filters is not None else PRESETS.get(preset or "growth", {})
    if _Overview is not None:
        out = _discover_finviz(filters_dict, signal, order, ascend, limit)
        if out:
            return out
    return _discover_yf(limit)
