"""
Pydantic schemas shared by the API and (eventually) the LangGraph agent
pipeline. This file is the contract between backend and frontend — treat
any field change here as a breaking change.
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
