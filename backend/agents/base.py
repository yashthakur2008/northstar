"""
Shared shape for the six specialist agents: fetch real data for a ticker,
hand it to the LLM to interpret, and return a structured AgentOpinion. Each
agents/<name>_agent.py file is a thin instantiation of this factory -- one
file per agent for discoverability, no duplicated logic between them.
"""

from __future__ import annotations

import json
from typing import Callable

from llm_client import call_llm, parse_json_response
from models import AgentOpinion

RESPONSE_INSTRUCTIONS = (
    "Respond with ONLY a JSON object (no markdown fences, no commentary) "
    "with exactly these keys: "
    '"stance" (one of "bullish", "bearish", "neutral"), '
    '"confidence" (a number from 0.0 to 1.0), '
    '"rationale" (2-3 sentences explaining the view, grounded in the data given).'
)


def run_data_agent(
    agent_name: str,
    symbol: str,
    fetch_data: Callable[[str], dict | None],
    system_prompt: str,
) -> AgentOpinion:
    try:
        data = fetch_data(symbol)
    except Exception as exc:
        return _unavailable(agent_name, symbol, f"Data fetch failed: {exc}")

    if not data:
        return _unavailable(agent_name, symbol, "No data returned for this ticker.")

    user_prompt = (
        f"Ticker: {symbol}\n\nData:\n{json.dumps(data, indent=2, default=str)}\n\n"
        f"{RESPONSE_INSTRUCTIONS}"
    )

    try:
        raw = call_llm(system=system_prompt, user=user_prompt)
        parsed = parse_json_response(raw)
        stance = parsed["stance"]
        if stance not in ("bullish", "bearish", "neutral"):
            stance = "neutral"
        return AgentOpinion(
            agent_name=agent_name,
            symbol=symbol,
            stance=stance,
            confidence=max(0.0, min(1.0, float(parsed["confidence"]))),
            rationale=str(parsed["rationale"]),
            data_available=True,
        )
    except Exception as exc:
        return _unavailable(agent_name, symbol, f"Agent reasoning failed: {exc}")


def _unavailable(agent_name: str, symbol: str, reason: str) -> AgentOpinion:
    return AgentOpinion(
        agent_name=agent_name,
        symbol=symbol,
        stance="neutral",
        confidence=0.0,
        rationale=reason,
        data_available=False,
    )
