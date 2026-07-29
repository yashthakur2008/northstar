"""
Risk metrics computed directly from yfinance price history -- trailing-year
annualized volatility and max drawdown. No separate API or key, consistent
with technical_data.py and options_data.py.
"""

from __future__ import annotations

import numpy as np
import yfinance as yf

TRADING_DAYS_PER_YEAR = 252


def get_risk_snapshot(symbol: str) -> dict | None:
    hist = yf.Ticker(symbol).history(period="1y", interval="1d")
    if hist is None or hist.empty or "Close" not in hist:
        return None

    closes = hist["Close"]
    daily_returns = closes.pct_change().dropna()
    if daily_returns.empty:
        return None

    annualized_volatility = float(daily_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))

    running_max = closes.cummax()
    drawdown = closes / running_max - 1
    max_drawdown_1y = float(drawdown.min())

    return {
        "annualized_volatility": round(annualized_volatility, 3),
        "max_drawdown_1y": round(max_drawdown_1y, 3),
    }
