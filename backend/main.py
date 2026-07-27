"""
FastAPI backend for the Multi-Agent Hedge Fund Analyzer.

Phase 2: /api/analyze runs the real LangGraph pipeline -- six specialist
agents, an N-round Bull/Bear debate, and a Portfolio Manager judge -- using
live data (yfinance, NewsAPI, FRED) and real LLM calls (Groq primary,
Gemini fallback). GROQ_API_KEY is required for any of it to work; the
other three keys (GEMINI_API_KEY, NEWSAPI_KEY, FRED_API_KEY) degrade
gracefully -- that one specialist returns a data_available=False opinion
rather than crashing the whole request -- if left unset. NEWSAPI_KEY's
free tier is dev/test only per NewsAPI.org's terms -- see
data_sources/news_data.py.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# No-op if backend/.env doesn't exist (e.g. on Render, where env vars come
# from the dashboard instead) -- only meaningful for local development.
# Every API key is read lazily inside a function body (see llm_client.py,
# data_sources/macro_data.py, data_sources/news_data.py), not at import
# time, so this doesn't strictly need to precede the imports below -- kept
# here anyway as the obvious place to look for it.
load_dotenv()

from graph import run_analysis  # noqa: E402
from models import AnalysisReport, AnalyzeRequest  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI(title="Multi-Agent Hedge Fund Analyzer", version="0.2.0")

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
    try:
        return run_analysis(request.tickers, request.debate_rounds)
    except Exception as exc:
        # A failure here means the pipeline itself couldn't complete (e.g.
        # no GROQ_API_KEY at all, so even the judge call fails) -- individual
        # specialist/data-source failures are already handled inside the
        # graph and surfaced as data_available=False opinions rather than
        # raised here.
        raise HTTPException(
            status_code=502, detail=f"Analysis pipeline failed: {exc}"
        ) from exc


# Registered last: routes above take priority, everything else falls
# through to the static frontend (index.html for `/`, plus its assets).
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
