"""Fundamentals specialist -- valuation and growth metrics from yfinance,
read for whether the company's financial quality supports the current
price."""

from __future__ import annotations

from agents.base import run_data_agent
from data_sources.market_data import get_fundamentals
from models import AgentOpinion

SYSTEM_PROMPT = (
    "You are the Fundamentals specialist on a hedge fund research desk. "
    "Look at this ticker's valuation multiples, growth, and profitability "
    "metrics and judge whether they support a bullish, bearish, or neutral "
    "view on the stock. Call out when a metric is missing rather than "
    "guessing at it."
)


def run(symbol: str) -> AgentOpinion:
    return run_data_agent("Fundamentals", symbol, get_fundamentals, SYSTEM_PROMPT)
