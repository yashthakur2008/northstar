"""
FastAPI backend for the Multi-Agent Hedge Fund Analyzer.

Phase 1: serves the static frontend and a mocked /api/analyze response so
the whole thing is deployable to Render on day one. Phase 2 replaces the
body of `analyze()` with a call into the LangGraph agent pipeline — the
route, request/response schema, and frontend do not need to change.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mock_data import generate_mock_report
from models import AnalysisReport, AnalyzeRequest

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI(title="Multi-Agent Hedge Fund Analyzer", version="0.1.0")

# Same-origin in this architecture (backend serves the frontend directly),
# so this is permissive by default rather than hardened. Tighten if the
# frontend ever moves to a separate origin/service.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalysisReport)
def analyze(request: AnalyzeRequest) -> AnalysisReport:
    # Phase 1: mocked so deployment + frontend contract can be validated
    # before the LangGraph pipeline, real data sources, and LLM calls exist.
    return generate_mock_report(request.tickers)


# Registered last: routes above take priority, everything else falls
# through to the static frontend (index.html for `/`, plus its assets).
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
