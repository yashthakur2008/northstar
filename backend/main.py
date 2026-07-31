"""FastAPI entrypoint for the multi-agent research desk."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from engine import AnalysisEngine
from models import AnalysisReport, AnalyzeRequest, AnalyzerPoint, MarketPulse, NewsItem, PricePoint, StockAnalysis, StockPulse
from providers import MarketDataError, fetch_resilient_analysis, fetch_yahoo_news

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
engine = AnalysisEngine()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="Trade Debate Desk API", version="1.0.0", docs_url="/api/docs", redoc_url=None)

allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"]
    )


@app.middleware("http")
async def prevent_mixed_frontend_versions(request, call_next):
    response = await call_next(request)
    if request.url.path in {"/", "/index.html", "/style.css", "/script.js"}:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version, "market_data": "Yahoo Finance with Nasdaq fallback"}


@app.get("/api/market-pulse", response_model=MarketPulse)
async def market_pulse(
    symbols: str = Query(
        default="SPY,QQQ,DIA,IWM,AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,BRK-B",
        max_length=120,
    ),
) -> MarketPulse:
    requested = list(dict.fromkeys(part.strip().upper() for part in symbols.split(",") if part.strip()))
    valid = [symbol for symbol in requested if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol)][:12]
    if not valid:
        valid = ["SPY", "QQQ", "DIA", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B"]
    snapshots, news_rows = await asyncio.gather(
        asyncio.gather(*(engine.provider.fetch(symbol) for symbol in valid), return_exceptions=True),
        asyncio.to_thread(fetch_yahoo_news),
    )
    stocks: list[StockPulse] = []
    for snapshot in snapshots:
        if isinstance(snapshot, Exception):
            continue
        stocks.append(StockPulse(
            symbol=snapshot.symbol,
            last_price=round(snapshot.last, 2),
            change_pct=round(snapshot.change_pct, 2),
            as_of=snapshot.as_of,
            source=snapshot.source,
            history=[
                PricePoint(timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc), close=round(price, 4))
                for timestamp, price in zip(snapshot.timestamps[-22:], snapshot.prices[-22:])
            ],
        ))
    news = [NewsItem(**row, is_trending=index < 2) for index, row in enumerate(news_rows)]
    status = "live" if len(stocks) == len(valid) and news else "partial" if stocks or news else "unavailable"
    return MarketPulse(stocks=stocks, news=news, generated_at=datetime.now(timezone.utc), source_status=status)


@app.get("/api/stock-analyzer", response_model=StockAnalysis)
async def stock_analyzer(
    symbol: str = Query(default="NVDA", min_length=1, max_length=10),
    period: Literal["1mo", "3mo", "6mo", "1y", "2y"] = "6mo",
    interval: Literal["1d", "1wk"] = "1d",
) -> StockAnalysis:
    normalized = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", normalized):
        raise HTTPException(status_code=422, detail="Enter a valid ticker symbol.")
    try:
        result = await asyncio.to_thread(fetch_resilient_analysis, normalized, period, interval)
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=f"Market history unavailable for {normalized}.") from exc
    rows = result["rows"]
    closes = [row["close"] for row in rows]
    returns = [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes))]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / max(len(returns) - 1, 1)
    annual_periods = 52 if interval == "1wk" else 252
    return StockAnalysis(
        symbol=normalized,
        period=period,
        interval=interval,
        currency=result["currency"],
        last_price=round(closes[-1], 2),
        change_pct=round(returns[-1] * 100, 2),
        period_return=round(((closes[-1] / closes[0]) - 1) * 100, 2),
        period_high=round(max(row["high"] for row in rows), 2),
        period_low=round(min(row["low"] for row in rows), 2),
        average_volume=round(sum(row["volume"] for row in rows) / len(rows)),
        volatility=round(math.sqrt(variance) * math.sqrt(annual_periods) * 100, 2),
        as_of=rows[-1]["timestamp"],
        source=result["source"],
        history=[AnalyzerPoint(**row) for row in rows],
    )


@app.post("/api/analyze", response_model=AnalysisReport)
async def analyze(request: AnalyzeRequest) -> AnalysisReport:
    return await engine.analyze(request)


@app.post("/api/analyze/stream")
async def analyze_stream(request: AnalyzeRequest) -> StreamingResponse:
    async def events():
        yield f"event: progress\ndata: {json.dumps({'current': 0, 'total': 1, 'percent': 2, 'stage': 'Opening the research desk'})}\n\n"
        report = await engine.analyze(request)
        total = len(report.debate)
        pacing = max(0.12, min(0.32, 8.0 / max(total, 1)))
        for index, message in enumerate(report.debate, start=1):
            stage = (
                f"{message.symbol} · Round {message.round} · {message.agent}"
                if message.round else f"{message.symbol} · {message.agent}"
            )
            yield f"event: progress\ndata: {json.dumps({'current': index - 1, 'total': total, 'percent': max(3, round((index - 1) / total * 96)), 'stage': stage})}\n\n"
            yield f"event: debate\ndata: {message.model_dump_json()}\n\n"
            await asyncio.sleep(pacing)
        yield f"event: progress\ndata: {json.dumps({'current': total, 'total': total, 'percent': 100, 'stage': 'Ranking complete'})}\n\n"
        yield f"event: report\ndata: {report.model_dump_json()}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
