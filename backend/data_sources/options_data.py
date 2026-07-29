"""
Options flow via yfinance's option chain -- free, no key. This resolves
the PRD's open question about where Options Flow data would come from:
real strikes, volume, open interest, and implied volatility for the
nearest expiration, at zero cost. Not the same as a dedicated "unusual
options activity" alert feed, but it's genuine live positioning data.
"""

from __future__ import annotations

import yfinance as yf


def get_options_snapshot(symbol: str) -> dict | None:
    ticker = yf.Ticker(symbol)
    expirations = ticker.options
    if not expirations:
        return None  # no listed options for this ticker

    nearest = expirations[0]
    chain = ticker.option_chain(nearest)
    calls, puts = chain.calls, chain.puts

    if calls is None or puts is None or (calls.empty and puts.empty):
        return None

    call_volume = int(calls["volume"].fillna(0).sum())
    put_volume = int(puts["volume"].fillna(0).sum())
    call_oi = int(calls["openInterest"].fillna(0).sum())
    put_oi = int(puts["openInterest"].fillna(0).sum())

    top_call_strike = None
    if not calls.empty and calls["openInterest"].notna().any():
        top_call_strike = float(calls.loc[calls["openInterest"].idxmax(), "strike"])

    top_put_strike = None
    if not puts.empty and puts["openInterest"].notna().any():
        top_put_strike = float(puts.loc[puts["openInterest"].idxmax(), "strike"])

    return {
        "nearest_expiration": nearest,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "put_call_volume_ratio": round(put_volume / call_volume, 2) if call_volume else None,
        "put_call_oi_ratio": round(put_oi / call_oi, 2) if call_oi else None,
        "top_open_interest_call_strike": top_call_strike,
        "top_open_interest_put_strike": top_put_strike,
        "avg_call_implied_vol": (
            round(float(calls["impliedVolatility"].mean()), 3) if not calls.empty else None
        ),
        "avg_put_implied_vol": (
            round(float(puts["impliedVolatility"].mean()), 3) if not puts.empty else None
        ),
    }
