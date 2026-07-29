"""Typed API contract for analysis, evidence and the agent debate."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class AnalyzeRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=1, max_length=5)
    debate_rounds: int = Field(default=4, ge=1, le=30)

    @field_validator("tickers")
    @classmethod
    def normalize_tickers(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().upper() for value in values))
        if not normalized or any(not TICKER_RE.fullmatch(value) for value in normalized):
            raise ValueError("Use 1–5 valid ticker symbols (letters, numbers, dot or hyphen).")
        return normalized


class Evidence(BaseModel):
    label: str
    value: str
    source: str
    as_of: datetime


class PricePoint(BaseModel):
    timestamp: datetime
    close: float = Field(gt=0)


class DebateScorePoint(BaseModel):
    round: int = Field(ge=1, le=30)
    bull: float = Field(ge=0, le=100)
    bear: float = Field(ge=0, le=100)
    net: float = Field(ge=-100, le=100)
    lens: str


class DebateMessage(BaseModel):
    sequence: int
    symbol: str
    agent: Literal["Market Data", "Technical", "Bull", "Bear", "Risk", "Portfolio Manager"]
    stance: Literal["process", "bull", "bear", "risk", "decision"]
    message: str
    round: int | None = None


class TradeIdea(BaseModel):
    symbol: str
    direction: Literal["long", "short", "watch"]
    actionability: Literal["candidate", "watchlist", "pass"]
    thesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=-100.0, le=100.0)
    last_price: float | None = None
    change_pct: float | None = None
    horizon: str = "1–3 months"
    key_risks: list[str]
    supporting_agents: list[str]
    dissenting_agents: list[str]
    evidence: list[Evidence] = Field(default_factory=list)
    price_history: list[PricePoint] = Field(default_factory=list)
    debate_scores: list[DebateScorePoint] = Field(default_factory=list)
    data_quality: Literal["live", "delayed", "unavailable"] = "unavailable"


class AnalysisReport(BaseModel):
    top_trades: list[TradeIdea]
    debate: list[DebateMessage]
    market_context: str
    generated_at: datetime
    methodology: str
    source_status: Literal["live", "partial", "unavailable"]
    is_mocked: bool = False


class StockPulse(BaseModel):
    symbol: str
    last_price: float = Field(gt=0)
    change_pct: float
    as_of: datetime
    source: str
    history: list[PricePoint]


class NewsItem(BaseModel):
    title: str
    publisher: str
    published_at: datetime
    url: str


class MarketPulse(BaseModel):
    stocks: list[StockPulse]
    news: list[NewsItem]
    generated_at: datetime
    source_status: Literal["live", "partial", "unavailable"]
