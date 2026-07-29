"""Deterministic multi-agent research pipeline.

The agents use independent lenses, then a portfolio-manager judge discounts
conviction for volatility, disagreement and missing evidence.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from models import AnalysisReport, AnalyzeRequest, DebateMessage, DebateScorePoint, Evidence, PricePoint, TradeIdea
from providers import MarketDataProvider, MarketSnapshot, ResilientMarketData


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _period_metrics(snapshot: MarketSnapshot, sessions: int) -> tuple[float, float, float, float, float]:
    prices = snapshot.prices[-(sessions + 1):]
    period_return = ((prices[-1] / prices[0]) - 1) * 100
    peak = prices[0]
    max_drawdown = 0.0
    returns: list[float] = []
    for index, price in enumerate(prices):
        peak = max(peak, price)
        max_drawdown = min(max_drawdown, ((price / peak) - 1) * 100)
        if index:
            returns.append((price / prices[index - 1]) - 1)
    if len(returns) < 2:
        volatility = 0.0
    else:
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        volatility = variance ** 0.5 * 252 ** 0.5 * 100
    positive_days = sum(value > 0 for value in returns) / max(len(returns), 1) * 100
    average_price = sum(prices) / len(prices)
    trend_gap = ((prices[-1] / average_price) - 1) * 100
    return period_return, volatility, max_drawdown, positive_days, trend_gap


def _round_windows(snapshot: MarketSnapshot, rounds: int) -> list[int]:
    maximum = min(len(snapshot.prices) - 1, 64)
    minimum = min(5, maximum)
    if rounds == 1 or maximum == minimum:
        return [min(22, maximum)]
    return [
        round(minimum + (maximum - minimum) * index / (rounds - 1))
        for index in range(rounds)
    ]


def _debate_scores(snapshot: MarketSnapshot, rounds: int) -> list[DebateScorePoint]:
    lenses = ("Momentum", "Drawdown", "Risk-adjusted trend")
    scores: list[DebateScorePoint] = []
    for round_number, sessions in enumerate(_round_windows(snapshot, rounds), start=1):
        period_return, volatility, max_drawdown, positive_days, trend_gap = _period_metrics(snapshot, sessions)
        breadth = (positive_days - 50) * 0.45
        drawdown_penalty = abs(max_drawdown) * 0.8
        volatility_penalty = max(volatility - 25, 0) * 0.12
        net = _clamp(period_return * 2.2 + trend_gap * 1.3 + breadth - drawdown_penalty - volatility_penalty, -90, 90)
        bull = round(_clamp(50 + net / 2, 5, 95), 1)
        scores.append(DebateScorePoint(
            round=round_number,
            bull=bull,
            bear=round(100 - bull, 1),
            net=round(net, 1),
            lens=lenses[(round_number - 1) % len(lenses)],
        ))
    return scores


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
    lenses = ("Momentum", "Drawdown", "Risk-adjusted trend")
    for round_number, sessions in enumerate(_round_windows(snapshot, rounds), start=1):
        period_return, period_volatility, max_drawdown, positive_days, trend_gap = _period_metrics(snapshot, sessions)
        lens = lenses[(round_number - 1) % len(lenses)]
        if lens == "Momentum":
            bull = (
                f"Round {round_number} · {lens}: the {sessions}-session return is {period_return:+.1f}%. "
                f"Advances occurred on {positive_days:.0f}% of sessions and price sits {trend_gap:+.1f}% versus "
                f"its window average. {'Breadth supports persistence.' if positive_days >= 50 else 'The case depends on a reversal broadening beyond a few sessions.'}"
            )
            bear = (
                f"Round {round_number} · {lens} rebuttal: {positive_days:.0f}% positive sessions do not establish "
                f"durability while annualized volatility is {period_volatility:.1f}% and maximum drawdown reached "
                f"{max_drawdown:.1f}%. The Bull case fails if breadth falls below 50% as price loses its window average."
            )
        elif lens == "Drawdown":
            bull = (
                f"Round {round_number} · {lens}: the {sessions}-session path returned {period_return:+.1f}% "
                f"after a {max_drawdown:.1f}% maximum drawdown. Price is now {trend_gap:+.1f}% versus its average, "
                "so stabilization above that reference would show that sellers are being absorbed."
            )
            bear = (
                f"Round {round_number} · {lens} rebuttal: the {max_drawdown:.1f}% peak-to-trough decline and "
                f"{period_volatility:.1f}% volatility define a loss path that the {period_return:+.1f}% return has "
                f"{'repaired' if period_return > abs(max_drawdown) else 'not repaired'}. A fresh low invalidates stabilization."
            )
        else:
            reward_to_risk = period_return / max(period_volatility, 1.0)
            bull = (
                f"Round {round_number} · {lens}: {period_return:+.1f}% over {sessions} sessions versus "
                f"{period_volatility:.1f}% volatility gives a {reward_to_risk:+.2f} return-to-risk reading; "
                f"price is {trend_gap:+.1f}% from its average with {positive_days:.0f}% positive sessions."
            )
            bear = (
                f"Round {round_number} · {lens} rebuttal: the {reward_to_risk:+.2f} reading is not compelling "
                f"unless return improves without volatility rising above {period_volatility:.1f}%. "
                "More upside accompanied by wider swings would be lower-quality evidence."
            )
        evidence_state = (
            "leans Bull" if period_return > 0 and trend_gap > 0 and positive_days >= 50
            else "leans Bear" if period_return < 0 and trend_gap < 0
            else "remains mixed"
        )
        daily_risk = period_volatility / 252 ** 0.5
        confirm_level = snapshot.last * (1 + daily_risk / 100)
        invalidate_level = snapshot.last * (1 - daily_risk / 100)
        risk = (
            f"Round {round_number} · Risk adjudication: evidence {evidence_state}. A close above "
            f"${confirm_level:,.2f} with positive-session breadth at or above 50% strengthens the Bull case; "
            f"a close below ${invalidate_level:,.2f} or a new {sessions}-session low strengthens the Bear case. "
            "These are monitoring thresholds, not price targets."
        )
        messages.extend([
            DebateMessage(sequence=seq, symbol=symbol, agent="Bull", stance="bull", round=round_number, message=bull),
            DebateMessage(sequence=seq + 1, symbol=symbol, agent="Bear", stance="bear", round=round_number, message=bear),
            DebateMessage(sequence=seq + 2, symbol=symbol, agent="Risk", stance="risk", round=round_number, message=risk),
        ])
        seq += 3
    round_returns = [_period_metrics(snapshot, window)[0] for window in _round_windows(snapshot, rounds)]
    positive_rounds = sum(value > 0 for value in round_returns)
    negative_rounds = sum(value < 0 for value in round_returns)
    messages.append(DebateMessage(
        sequence=seq, symbol=symbol, agent="Risk", stance="risk",
        message=(
            f"Final risk synthesis: {positive_rounds} of {rounds} windows were positive and "
            f"{negative_rounds} were negative; full-period volatility is {volatility:.1f}%. "
            "Conviction is reduced for disagreement and for missing fundamental, valuation, catalyst, liquidity, "
            "borrow and options evidence. Treat the result as a screen until those gaps are closed."
        ),
    ))
    return messages


def _judge(snapshot: MarketSnapshot, messages: list[DebateMessage], rounds: int) -> TradeIdea:
    momentum = snapshot.return_1m
    vol = snapshot.volatility
    round_returns = [_period_metrics(snapshot, window)[0] for window in _round_windows(snapshot, rounds)]
    multi_horizon = sum(round_returns) / len(round_returns)
    raw_score = _clamp((momentum * 2.0) + multi_horizon, -80, 80)
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
        f"Screen-grade {stance} setup: {snapshot.return_1m:+.1f}% one-month momentum and "
        f"{multi_horizon:+.1f}% average return across {rounds} research window{'s' if rounds != 1 else ''}, "
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
    price_history = [
        PricePoint(
            timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc),
            close=round(price, 4),
        )
        for timestamp, price in zip(snapshot.timestamps, snapshot.prices)
    ]
    supporters = ["Technical"] + (["Bull"] if score > 0 else ["Bear"] if score < 0 else [])
    dissenters = ["Bear"] if score > 0 else ["Bull"] if score < 0 else ["Bull", "Bear"]
    return TradeIdea(
        symbol=snapshot.symbol, direction=direction, actionability=actionability, thesis=thesis,
        confidence=confidence, score=score, last_price=round(snapshot.last, 2),
        change_pct=round(snapshot.change_pct, 2), key_risks=risks,
        supporting_agents=supporters, dissenting_agents=dissenters, evidence=evidence,
        price_history=price_history, debate_scores=_debate_scores(snapshot, rounds), data_quality="live",
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
            trade = _judge(outcome, symbol_debate, request.debate_rounds)
            sequence = symbol_debate[-1].sequence + 1
            debate.append(DebateMessage(
                sequence=sequence, symbol=symbol, agent="Portfolio Manager", stance="decision",
                message=f"Decision: {trade.actionability.upper()} / {trade.direction.upper()}, score {trade.score:+.1f}, confidence {trade.confidence:.0%}.",
            ))
            sequence += 1
            trades.append(trade)
        trades.sort(key=lambda item: (abs(item.score), item.confidence), reverse=True)
        status = "live" if trades and not failed else "partial" if trades else "unavailable"
        failed_note = f" Data unavailable for {', '.join(failed)}." if failed else ""
        return AnalysisReport(
            top_trades=trades,
            debate=debate,
            market_context="Screen-grade market analysis using recent daily prices; not a full investment recommendation." + failed_note,
            generated_at=datetime.now(timezone.utc),
            methodology="Conviction ranking blends one-month momentum with the average return across every round's distinct rolling window, then applies a realized-volatility haircut. Confidence is capped at 82%.",
            source_status=status,
            is_mocked=False,
        )
