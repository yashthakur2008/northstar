"""
Fundamentals via yfinance's `Ticker.info` -- price, valuation, and growth
metrics with no separate API key. `Ticker.info` is a single scraped
snapshot, not a paid fundamentals feed, so treat these as directional
signals for the LLM rather than audited financials.
"""

from __future__ import annotations

import yfinance as yf


def get_fundamentals(symbol: str) -> dict | None:
    info = yf.Ticker(symbol).info
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not info or price is None:
        return None

    return {
        "price": price,
        "market_cap": info.get("marketCap"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "price_to_book": info.get("priceToBook"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "profit_margin": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "free_cashflow": info.get("freeCashflow"),
    }
