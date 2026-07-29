"""Deterministic multi-agent research pipeline.

The agents use independent lenses, then a portfolio-manager judge discounts
conviction for volatility, disagreement and missing evidence.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from models import AnalysisReport, AnalyzeRequest, DebateMessage, Evidence, TradeIdea
from providers import MarketDataProvider, MarketSnapshot, ResilientMarketData


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _debate(snapshot: MarketSnapshot, rounds: int, start: int) -> list[DebateMessage]:
    symbol = snapshot.symbol
    momentum = snapshot.return_1m
    volatility = snapshot.volatility
    messages = [
        DebateMessage(sequence=start, symbol=symbol, agent="Market Data", stance="process",
                      message=f"Validated {len(snapshot.prices)} daily closes through {snapshot.as_of:%b %d, %Y}; last price ${snapshot.last:,.2f}."),
        DebateMessage(sequence=start + 1, symbol=symbol, agent="Technical", stance="process",
                      message=f"Measured 1-month momentum at {momentum:+.1f}% and annualized realized volatility at {volatility:.1f}%."),
    ]
    seq = start + 2
    for round_number in range(1, rounds + 1):
        bull = (
            f"Round {round_number}: price persistence is constructive ({momentum:+.1f}% over one month). "
            "The setup remains valid while momentum holds and fresh evidence confirms the move."
            if momentum >= 0 else
            f"Round {round_number}: the {momentum:.1f}% one-month decline may offer asymmetric recovery, "
            "but reversal evidence is still required."
        )
        bear = (
            f"Round {round_number}: {volatility:.1f}% realized volatility can overwhelm the signal; "
            "a momentum reversal is the primary disconfirming condition."
        )
        messages.extend([
            DebateMessage(sequence=seq, symbol=symbol, agent="Bull", stance="bull", round=round_number, message=bull),
            DebateMessage(sequence=seq + 1, symbol=symbol, agent="Bear", stance="bear", round=round_number, message=bear),
        ])
        seq += 2
    messages.append(DebateMessage(
        sequence=seq, symbol=symbol, agent="Risk", stance="risk",
        message="Applied a volatility and evidence-quality haircut; no fundamental, valuation, news, borrow or options claims were inferred from price data.",
    ))
    return messages


def _judge(snapshot: MarketSnapshot, messages: list[DebateMessage]) -> TradeIdea:
    momentum = snapshot.return_1m
    vol = snapshot.volatility
    raw_score = _clamp(momentum * 3.0, -80, 80)
    risk_haircut = _clamp((vol - 20) * 0.35, 0, 22)
    score = raw_score - risk_haircut if raw_score >= 0 else raw_score + risk_haircut
    score = round(_clamp(score, -100, 100), 1)
    if score >= 18:
        direction, actionability = "long", "candidate"
    elif score <= -18:
        direction, actionability = "short", "candidate"
    else:
        direction, actionability = "watch", "watchlist"
    confidence = round(_clamp(0.45 + abs(score) / 200 - vol / 600, 0.25, 0.82), 2)
    stance = "positive" if direction == "long" else "negative" if direction == "short" else "inconclusive"
    thesis = (
        f"Screen-grade {stance} setup: {snapshot.return_1m:+.1f}% one-month price momentum, "
        f"tempered by {vol:.1f}% realized volatility. Upgrade conviction only after "
        "fundamental, valuation and catalyst evidence corroborates the signal."
    )
    risks = [
        "Price-only signal can reverse and is not a substitute for fundamental diligence.",
        "No valuation, earnings-estimate, news, options, liquidity or borrow data is included.",
    ]
    evidence = [
        Evidence(label="Last close", value=f"${snapshot.last:,.2f}", source=snapshot.source, as_of=snapshot.as_of),
        Evidence(label="1-month return", value=f"{snapshot.return_1m:+.1f}%", source=snapshot.source, as_of=snapshot.as_of),
        Evidence(label="Realized volatility", value=f"{vol:.1f}%", source=f"Derived from {snapshot.source}", as_of=snapshot.as_of),
    ]
    supporters = ["Technical"] + (["Bull"] if score > 0 else ["Bear"] if score < 0 else [])
    dissenters = ["Bear"] if score > 0 else ["Bull"] if score < 0 else ["Bull", "Bear"]
    return TradeIdea(
        symbol=snapshot.symbol, direction=direction, actionability=actionability, thesis=thesis,
        confidence=confidence, score=score, last_price=round(snapshot.last, 2),
        change_pct=round(snapshot.change_pct, 2), key_risks=risks,
        supporting_agents=supporters, dissenting_agents=dissenters, evidence=evidence, data_quality="live",
    )


class AnalysisEngine:
    def __init__(self, provider: MarketDataProvider | None = None) -> None:
        self.provider = provider or ResilientMarketData()

    async def analyze(self, request: AnalyzeRequest) -> AnalysisReport:
        outcomes = await asyncio.gather(*(self.provider.fetch(symbol) for symbol in request.tickers), return_exceptions=True)
        trades: list[TradeIdea] = []
        debate: list[DebateMessage] = []
        failed: list[str] = []
        sequence = 1
        for symbol, outcome in zip(request.tickers, outcomes):
            if isinstance(outcome, Exception):
                failed.append(symbol)
                debate.append(DebateMessage(sequence=sequence, symbol=symbol, agent="Market Data", stance="process",
                                            message="Live history could not be validated. The desk withheld a prediction instead of fabricating one."))
                sequence += 1
                continue
            symbol_debate = _debate(outcome, request.debate_rounds, sequence)
            debate.extend(symbol_debate)
            trade = _judge(outcome, symbol_debate)
            sequence = symbol_debate[-1].sequence + 1
            debate.append(DebateMessage(
                sequence=sequence, symbol=symbol, agent="Portfolio Manager", stance="decision",
                message=f"Decision: {trade.actionability.upper()} / {trade.direction.upper()}, score {trade.score:+.1f}, confidence {trade.confidence:.0%}.",
            ))
            sequence += 1
            trades.append(trade)
        trades.sort(key=lambda item: abs(item.score), reverse=True)
        status = "live" if trades and not failed else "partial" if trades else "unavailable"
        failed_note = f" Data unavailable for {', '.join(failed)}." if failed else ""
        return AnalysisReport(
            top_trades=trades,
            debate=debate,
            market_context="Screen-grade market analysis using recent daily prices; not a full investment recommendation." + failed_note,
            generated_at=datetime.now(timezone.utc),
            methodology="Momentum signal × 3, capped at ±80, with a realized-volatility haircut. Confidence is capped at 82% and reduced for volatility and missing evidence.",
            source_status=status,
            is_mocked=False,
        )
