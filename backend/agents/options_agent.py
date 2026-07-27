"""Options Flow specialist -- put/call volume and open-interest positioning
from the nearest listed expiration, read as a positioning signal."""

from __future__ import annotations

from agents.base import run_data_agent
from data_sources.options_data import get_options_snapshot
from models import AgentOpinion

SYSTEM_PROMPT = (
    "You are the Options Flow specialist on a hedge fund research desk. "
    "Look at this ticker's put/call volume and open-interest ratios and the "
    "strikes with the heaviest positioning, and judge whether options "
    "market positioning leans bullish, bearish, or neutral. Note that a "
    "put-heavy book can also mean hedging rather than a bearish bet -- say "
    "so if the data is ambiguous."
)


def run(symbol: str) -> AgentOpinion:
    return run_data_agent("OptionsFlow", symbol, get_options_snapshot, SYSTEM_PROMPT)
