"""FastAPI entrypoint for the multi-agent research desk."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from engine import AnalysisEngine
from models import AnalysisReport, AnalyzeRequest

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


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version, "market_data": "Yahoo Finance with Nasdaq fallback"}


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
