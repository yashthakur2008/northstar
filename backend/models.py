"""
Pydantic schemas shared across the API and the LangGraph agent pipeline.
`AnalyzeRequest` / `AnalysisReport` are the API contract (backend/frontend
must both conform to these). `AgentOpinion` and `DebateTurn` are internal
to the pipeline (specialist agents and the Bull/Bear debate) and are not
exposed directly over the API, but are shared here since both the graph
and the judge need the same shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=1, max_length=5)
    debate_rounds: int = Field(default=2, ge=1, le=4)


class TradeIdea(BaseModel):
    symbol: str
    direction: Literal["long", "short", "options_spread"]
    thesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    key_risks: list[str]
    supporting_agents: list[str]
    dissenting_agents: list[str]


class AnalysisReport(BaseModel):
    top_trades: list[TradeIdea]
    market_context: str
    generated_at: datetime
    is_mocked: bool = False


class AgentOpinion(BaseModel):
    """One specialist agent's structured view on one ticker. `data_available`
    is False when the underlying data fetch or the LLM call failed -- the
    opinion is still returned (as neutral/0 confidence) so a single failed
    data source doesn't take down the whole analysis, but the judge and the
    debate agents can see it was a non-answer rather than a real neutral
    call."""

    agent_name: str
    symbol: str
    stance: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    data_available: bool = True


class DebateTurn(BaseModel):
    round: int
    role: Literal["bull", "bear"]
    argument: str
