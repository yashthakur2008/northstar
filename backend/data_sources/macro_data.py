"""
Macro backdrop via the official FRED (Federal Reserve Economic Data) API.
Free, unlimited, no production-use restriction -- unlike NewsAPI.org, FRED
has no localhost-only clause in its terms. Requires a free API key
(FRED_API_KEY), registered at fred.stlouisfed.org.
"""

from __future__ import annotations

import os

import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Ticker-independent -- these describe the overall macro backdrop, not any
# single company. `get_macro_snapshot(symbol)` still takes a symbol so its
# signature matches every other data-source function that agents/base.py
# calls uniformly.
SERIES = {
    "10y_treasury_yield": "DGS10",
    "fed_funds_rate": "FEDFUNDS",
    "cpi_index": "CPIAUCSL",
    "unemployment_rate": "UNRATE",
}


def _latest_observation(series_id: str, api_key: str) -> float | None:
    resp = requests.get(
        FRED_BASE,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    if not observations:
        return None
    value = observations[0].get("value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None  # FRED represents missing data points as "."


def get_macro_snapshot(_symbol: str) -> dict | None:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        return None

    snapshot = {label: _latest_observation(series_id, api_key) for label, series_id in SERIES.items()}
    if all(v is None for v in snapshot.values()):
        return None
    return snapshot
