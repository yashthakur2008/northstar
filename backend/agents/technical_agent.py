"""Technical specialist -- moving averages, RSI, and MACD computed from
price history, read for trend and momentum."""

from __future__ import annotations

from agents.base import run_data_agent
from data_sources.technical_data import get_technical_snapshot
from models import AgentOpinion

SYSTEM_PROMPT = (
    "You are the Technical Analysis specialist on a hedge fund research "
    "desk. Look at this ticker's moving averages, RSI, and MACD and judge "
    "whether the price action and momentum are bullish, bearish, or "
    "neutral. Ground your rationale in the specific indicator values given, "
    "not generic chart-pattern language."
)


def run(symbol: str) -> AgentOpinion:
    return run_data_agent("Technical", symbol, get_technical_snapshot, SYSTEM_PROMPT)
