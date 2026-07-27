"""
Bull and Bear researcher agents. Each debate round, both read the
specialist opinions plus the transcript so far and argue their side -- the
system prompts explicitly require engaging with the other side's specific
point, so the transcript is a real argument rather than two monologues.
"""

from __future__ import annotations

import json

from llm_client import call_llm, parse_json_response
from models import AgentOpinion, DebateTurn

ARGUMENT_INSTRUCTIONS = (
    "Respond with ONLY a JSON object with one key: "
    '"argument" (3-5 sentences). Reference at least one specific point '
    "from the agent opinions, or directly rebut the other side's prior "
    "argument if one exists -- do not write generic commentary."
)

BULL_SYSTEM = (
    "You are the Bull Researcher on a hedge fund research desk debating a "
    "single trade idea. Build the strongest honest case FOR taking a long "
    "position, using the specialist agents' opinions as your evidence. If "
    "the Bear has already spoken this debate, directly rebut their "
    "strongest point rather than ignoring it."
)

BEAR_SYSTEM = (
    "You are the Bear Researcher on a hedge fund research desk debating a "
    "single trade idea. Build the strongest honest case AGAINST taking a "
    "long position (or FOR shorting), using the specialist agents' "
    "opinions as your evidence. Directly rebut the Bull's strongest point "
    "from this round rather than repeating generic caution."
)


def _run_side(
    role: str,
    system_prompt: str,
    symbol: str,
    opinions: list[AgentOpinion],
    transcript: list[DebateTurn],
    round_number: int,
) -> DebateTurn:
    opinions_json = json.dumps([o.model_dump() for o in opinions], indent=2, default=str)
    transcript_json = json.dumps([t.model_dump() for t in transcript], indent=2, default=str)

    user_prompt = (
        f"Ticker: {symbol}\nRound: {round_number}\n\n"
        f"Specialist agent opinions:\n{opinions_json}\n\n"
        f"Debate so far:\n{transcript_json or '(no prior rounds)'}\n\n"
        f"{ARGUMENT_INSTRUCTIONS}"
    )

    try:
        raw = call_llm(system=system_prompt, user=user_prompt)
        parsed = parse_json_response(raw)
        argument = str(parsed["argument"])
    except Exception as exc:
        argument = f"[{role} argument unavailable: {exc}]"

    return DebateTurn(round=round_number, role=role, argument=argument)


def run_bull(
    symbol: str, opinions: list[AgentOpinion], transcript: list[DebateTurn], round_number: int
) -> DebateTurn:
    return _run_side("bull", BULL_SYSTEM, symbol, opinions, transcript, round_number)


def run_bear(
    symbol: str, opinions: list[AgentOpinion], transcript: list[DebateTurn], round_number: int
) -> DebateTurn:
    return _run_side("bear", BEAR_SYSTEM, symbol, opinions, transcript, round_number)
