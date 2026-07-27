"""Risk specialist -- trailing-year annualized volatility and max drawdown,
read for how much conviction the position's risk profile can support."""

from __future__ import annotations

from agents.base import run_data_agent
from data_sources.risk_data import get_risk_snapshot
from models import AgentOpinion

SYSTEM_PROMPT = (
    "You are the Risk specialist on a hedge fund research desk. Look at "
    "this ticker's trailing annualized volatility and max drawdown over "
    "the past year, and judge whether the risk profile is bullish (low "
    "risk supports a confident position), bearish (elevated risk argues "
    "against sizing up or holding long), or neutral. High volatility alone "
    "isn't automatically bearish -- weigh it against what the other "
    "specialists are seeing, if mentioned."
)


def run(symbol: str) -> AgentOpinion:
    return run_data_agent("Risk", symbol, get_risk_snapshot, SYSTEM_PROMPT)
