"""
Portfolio Manager (judge) agent. Reads every ticker's specialist opinions
and full debate transcript, and picks the top trades across the whole
batch -- not one per ticker, since the point is cross-ticker ranking.
"""

from __future__ import annotations

import json

from llm_client import call_llm, parse_json_response
from models import AgentOpinion, DebateTurn, TradeIdea

SYSTEM_PROMPT = (
    "You are the Portfolio Manager on a hedge fund research desk. You have "
    "the specialist agent opinions and full Bull/Bear debate transcript "
    "for each candidate ticker. Weigh the quality of argument, not just "
    "which side had more words -- a well-evidenced dissent should count. "
    "Pick the best trade ideas across ALL tickers combined, not one per "
    "ticker. It is fine to return fewer than 3 if the evidence for the "
    "others is too weak or too mixed to support a real trade idea."
)

RESPONSE_INSTRUCTIONS = (
    "Respond with ONLY a JSON object with two top-level keys: "
    '"trades": an array of up to 3 objects (ranked best first), each with '
    'keys "symbol", "direction" (one of "long", "short", "options_spread"), '
    '"thesis" (2-4 sentences), "confidence" (0.0-1.0), '
    '"key_risks" (array of 1-3 short strings), '
    '"supporting_agents" (array of agent names whose view backs this call), '
    '"dissenting_agents" (array of agent names whose view opposed it); and '
    '"market_context": a 2-3 sentence summary of the overall backdrop '
    "across these tickers."
)


def run_judge(
    all_opinions: dict[str, list[AgentOpinion]],
    all_transcripts: dict[str, list[DebateTurn]],
) -> tuple[list[TradeIdea], str]:
    payload = {
        symbol: {
            "opinions": [o.model_dump() for o in all_opinions.get(symbol, [])],
            "debate": [t.model_dump() for t in all_transcripts.get(symbol, [])],
        }
        for symbol in all_opinions
    }

    user_prompt = (
        f"Candidate tickers and their full research:\n"
        f"{json.dumps(payload, indent=2, default=str)}\n\n"
        f"{RESPONSE_INSTRUCTIONS}"
    )

    raw = call_llm(system=SYSTEM_PROMPT, user=user_prompt)
    parsed = parse_json_response(raw)

    trades: list[TradeIdea] = []
    for candidate in parsed.get("trades", [])[:3]:
        try:
            trades.append(TradeIdea(**candidate))
        except Exception:
            # Skip a single malformed trade rather than failing the whole
            # request over one bad field in an otherwise-good response.
            continue

    market_context = str(parsed.get("market_context", ""))
    return trades, market_context
