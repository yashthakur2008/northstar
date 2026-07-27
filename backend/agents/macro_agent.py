"""Macro specialist -- rates, inflation, and unemployment from FRED, read
for the backdrop the ticker is trading against rather than anything
company-specific."""

from __future__ import annotations

from agents.base import run_data_agent
from data_sources.macro_data import get_macro_snapshot
from models import AgentOpinion

SYSTEM_PROMPT = (
    "You are the Macro specialist on a hedge fund research desk. Look at "
    "the current 10-year Treasury yield, fed funds rate, CPI, and "
    "unemployment rate, and judge whether the macro backdrop is bullish, "
    "bearish, or neutral for this specific ticker given its sector's "
    "typical rate- and growth-sensitivity."
)


def run(symbol: str) -> AgentOpinion:
    return run_data_agent("Macro", symbol, get_macro_snapshot, SYSTEM_PROMPT)
