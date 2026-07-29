"""
Offline integration test. Stubs every network call (the six data_sources
fetch functions + the LLM client) so the full pipeline -- specialist
agents -> debate loop -> judge -> FastAPI endpoint -- can be exercised
without internet access. This validates the plumbing (Pydantic models,
the agent factory, LangGraph wiring, error handling, the endpoint) is
correct; it does NOT validate that yfinance/Finnhub/FRED/Groq/Gemini
still behave exactly as documented against the live internet -- that
needs a real run with real keys.

Not part of the shipped app -- delete or move to a tests/ dir with real
pytest fixtures once the pipeline is confirmed working live.
"""

from __future__ import annotations

import json
from unittest.mock import patch

FAKE_FUNDAMENTALS = {"price": 150.0, "trailing_pe": 25.0, "revenue_growth": 0.12}
FAKE_TECHNICALS = {"last_close": 150.0, "rsi_14": 55.0, "macd": 1.2, "macd_signal": 0.8}
FAKE_OPTIONS = {"put_call_volume_ratio": 0.7, "top_open_interest_call_strike": 160.0}
FAKE_MACRO = {"10y_treasury_yield": 4.1, "fed_funds_rate": 4.5}
FAKE_NEWS = {"headlines": [{"headline": "Company beats earnings", "source": "Reuters", "summary": "..."}]}
FAKE_RISK = {"annualized_volatility": 0.28, "max_drawdown_1y": -0.15}


def fake_call_llm(system: str, user: str) -> str:
    """Deterministic stand-in for the LLM. Returns valid JSON matching
    whichever schema the calling prompt asked for, inferred from the
    prompt text -- good enough to exercise every code path (specialist
    opinion, bull argument, bear argument, judge synthesis) without a
    real model."""
    if '"argument"' in user or "argument" in system.lower() and "Bull" in system or "Bear" in system:
        pass  # fallthrough handled below by more specific checks first

    if "Portfolio Manager" in system:
        return json.dumps(
            {
                "trades": [
                    {
                        "symbol": "AAPL",
                        "direction": "long",
                        "thesis": "Strong fundamentals and supportive options positioning outweigh macro headwinds.",
                        "confidence": 0.72,
                        "key_risks": ["Rate sensitivity", "Valuation is not cheap"],
                        "supporting_agents": ["Fundamentals", "Technical"],
                        "dissenting_agents": ["Macro"],
                    }
                ],
                "market_context": "Mixed macro backdrop with resilient large-cap fundamentals.",
            }
        )

    if "Bull Researcher" in system:
        return json.dumps({"argument": "Fundamentals show healthy revenue growth, and options flow leans bullish."})

    if "Bear Researcher" in system:
        return json.dumps({"argument": "Valuation is stretched and macro conditions add rate-sensitivity risk."})

    # Specialist agent (news/fundamentals/technical/options/macro/risk)
    return json.dumps(
        {
            "stance": "bullish",
            "confidence": 0.65,
            "rationale": "Data supports a constructive near-term view based on the figures provided.",
        }
    )


def run():
    with (
        patch("data_sources.market_data.get_fundamentals", return_value=FAKE_FUNDAMENTALS),
        patch("data_sources.technical_data.get_technical_snapshot", return_value=FAKE_TECHNICALS),
        patch("data_sources.options_data.get_options_snapshot", return_value=FAKE_OPTIONS),
        patch("data_sources.macro_data.get_macro_snapshot", return_value=FAKE_MACRO),
        patch("data_sources.news_data.get_recent_news", return_value=FAKE_NEWS),
        patch("data_sources.risk_data.get_risk_snapshot", return_value=FAKE_RISK),
        patch("agents.base.call_llm", side_effect=fake_call_llm),
        patch("agents.debate.call_llm", side_effect=fake_call_llm),
        patch("agents.judge.call_llm", side_effect=fake_call_llm),
    ):
        # --- Layer 1: graph.run_analysis() directly ---
        from graph import run_analysis

        report = run_analysis(tickers=["AAPL"], debate_rounds=2)
        assert report.is_mocked is False
        assert len(report.top_trades) == 1
        assert report.top_trades[0].symbol == "AAPL"
        assert report.market_context
        print("[OK] graph.run_analysis() produced a valid AnalysisReport")
        print("     ->", report.top_trades[0].model_dump())

        # --- Layer 2: the actual FastAPI endpoint via TestClient ---
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        print("[OK] GET /api/health")

        resp = client.post("/api/analyze", json={"tickers": ["AAPL", "NVDA"], "debate_rounds": 1})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_mocked"] is False
        assert isinstance(body["top_trades"], list)
        print("[OK] POST /api/analyze ->", json.dumps(body, indent=2)[:400], "...")

        frontend = client.get("/")
        assert frontend.status_code == 200
        assert "Trade Debate Desk" in frontend.text
        print("[OK] GET / serves the frontend")

    print("\nAll offline integration checks passed.")


if __name__ == "__main__":
    run()
