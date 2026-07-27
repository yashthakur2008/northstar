"""News specialist -- recent headlines via Finnhub, read for sentiment and
market-moving relevance rather than just keyword counting."""

from __future__ import annotations

from agents.base import run_data_agent
from data_sources.news_data import get_recent_news
from models import AgentOpinion

SYSTEM_PROMPT = (
    "You are the News specialist on a hedge fund research desk. Read the "
    "recent headlines for this ticker and judge whether the news flow is "
    "bullish, bearish, or neutral for the stock over the next few weeks. "
    "Weigh recency and the credibility of the source over any single "
    "attention-grabbing headline."
)


def run(symbol: str) -> AgentOpinion:
    return run_data_agent("News", symbol, get_recent_news, SYSTEM_PROMPT)
