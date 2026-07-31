from datetime import datetime, timezone

from fastapi.testclient import TestClient

import main
from engine import AnalysisEngine
from main import app
from models import AnalyzeRequest
from providers import MarketDataError, MarketSnapshot, ResilientMarketData, YahooMarketData


class StubProvider:
    async def fetch(self, symbol: str) -> MarketSnapshot:
        prices = tuple(100 + index * 0.5 for index in range(45))
        timestamps = tuple(1_700_000_000 + index * 86_400 for index in range(45))
        return MarketSnapshot(symbol=symbol, prices=prices, timestamps=timestamps, source="Test fixture")


class FailedProvider:
    async def fetch(self, symbol: str) -> MarketSnapshot:
        raise MarketDataError("Test provider", symbol, "offline")


def test_health() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["version"] == "1.0.0"


def test_frontend_assets_cannot_mix_across_deployments() -> None:
    client = TestClient(app)
    page = client.get("/")
    stylesheet = client.get("/style.css")
    script = client.get("/script.js")
    assert "no-store" in page.headers["cache-control"]
    assert "no-store" in stylesheet.headers["cache-control"]
    assert "no-store" in script.headers["cache-control"]
    assert "style.css?v=20260731h" in page.text
    assert "script.js?v=20260731g" in page.text
    assert "How to use Northstar" in page.text
    assert "Research systems operational" not in page.text


def test_all_news_page_is_available() -> None:
    page = TestClient(app).get("/news.html")
    assert page.status_code == 200
    assert "Market news" in page.text
    assert "news.js?v=20260731g" in page.text
    assert 'id="theme-toggle"' in page.text
    assert "site-shell.js?v=20260731g" in page.text


def test_beginner_guide_is_publicly_available() -> None:
    page = TestClient(app).get("/beginners.html")
    assert page.status_code == 200
    assert "Your first stock analysis" in page.text
    assert "What is a stock ticker?" in page.text
    assert "Signal score" in page.text
    assert 'id="theme-toggle"' in page.text
    assert "site-shell.js?v=20260731g" in page.text


def test_request_validation() -> None:
    client = TestClient(app)
    assert client.post("/api/analyze", json={"tickers": ["bad ticker"]}).status_code == 422
    assert client.post("/api/analyze", json={"tickers": ["A", "B", "C", "D", "E", "F"]}).status_code == 422
    assert client.post("/api/analyze", json={"tickers": ["A"], "debate_rounds": 31}).status_code == 422


def test_market_pulse_is_typed_and_resilient(monkeypatch) -> None:
    previous_provider = main.engine.provider
    main.engine.provider = StubProvider()
    monkeypatch.setattr(main, "fetch_yahoo_news", lambda *args: [{
        "title": "Markets test headline",
        "publisher": "Test publisher",
        "published_at": datetime.now(timezone.utc),
        "url": "https://example.com/story",
    }])
    try:
        response = TestClient(app).get("/api/market-pulse?symbols=TEST,TEST")
    finally:
        main.engine.provider = previous_provider
    assert response.status_code == 200
    body = response.json()
    assert body["source_status"] == "live"
    assert len(body["stocks"]) == 1
    assert body["stocks"][0]["symbol"] == "TEST"
    assert len(body["stocks"][0]["history"]) == 22
    assert body["news"][0]["publisher"] == "Test publisher"


def test_stock_analyzer_returns_ohlcv_metrics(monkeypatch) -> None:
    rows = [
        {
            "timestamp": datetime.fromtimestamp(1_700_000_000 + index * 86_400, tz=timezone.utc),
            "open": 100.0 + index,
            "high": 102.0 + index,
            "low": 99.0 + index,
            "close": 101.0 + index,
            "volume": 1_000_000 + index * 10_000,
        }
        for index in range(12)
    ]
    monkeypatch.setattr(main, "fetch_resilient_analysis", lambda symbol, period, interval: {
        "symbol": symbol,
        "currency": "USD",
        "rows": rows,
        "source": "Test chart source",
    })
    response = TestClient(app).get("/api/stock-analyzer?symbol=TEST&period=6mo&interval=1d")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TEST"
    assert body["period"] == "6mo"
    assert len(body["history"]) == 12
    assert body["period_high"] == 113.0
    assert body["period_low"] == 99.0
    assert body["average_volume"] > 1_000_000
    assert body["volatility"] >= 0


async def test_engine_is_deterministic_and_traced() -> None:
    report = await AnalysisEngine(StubProvider()).analyze(AnalyzeRequest(tickers=["TEST"], debate_rounds=2))
    assert report.source_status == "live"
    assert report.is_mocked is False
    assert len(report.top_trades) == 1
    assert report.top_trades[0].confidence <= 0.82
    assert len(report.top_trades[0].price_history) == 45
    assert report.top_trades[0].price_history[-1].close == 122.0
    assert len(report.top_trades[0].debate_scores) == 2
    assert all(point.bull + point.bear == 100 for point in report.top_trades[0].debate_scores)
    assert all(-100 <= point.net <= 100 for point in report.top_trades[0].debate_scores)
    assert report.debate[-1].agent == "Portfolio Manager"
    assert all(item.source for item in report.top_trades[0].evidence)
    round_messages = [event.message for event in report.debate if event.round]
    assert len(round_messages) == 6
    assert len(set(round_messages)) == 6
    assert [event.agent for event in report.debate if event.round][:3] == ["Bull", "Bear", "Risk"]


async def test_engine_withholds_when_source_fails() -> None:
    report = await AnalysisEngine(FailedProvider()).analyze(AnalyzeRequest(tickers=["TEST"], debate_rounds=1))
    assert report.source_status == "unavailable"
    assert report.top_trades == []
    assert "withheld" in report.debate[0].message.lower()


async def test_provider_cache_avoids_duplicate_calls() -> None:
    provider = YahooMarketData(cache_ttl=60)
    calls = 0

    def fake_fetch(symbol: str) -> MarketSnapshot:
        nonlocal calls
        calls += 1
        return StubProviderSnapshot(symbol)

    provider._fetch_sync = fake_fetch
    await provider.fetch("TEST")
    await provider.fetch("TEST")
    assert calls == 1


async def test_resilient_provider_falls_back() -> None:
    provider = ResilientMarketData(providers=(FailedProvider(), StubProvider()))
    snapshot = await provider.fetch("TEST")
    assert snapshot.source == "Test fixture"


async def test_thirty_rounds_are_distinct_and_complete() -> None:
    report = await AnalysisEngine(StubProvider()).analyze(AnalyzeRequest(tickers=["TEST"], debate_rounds=30))
    bull_messages = [event.message for event in report.debate if event.agent == "Bull"]
    risk_messages = [event.message for event in report.debate if event.agent == "Risk" and event.round]
    assert len(bull_messages) == 30
    assert len(set(bull_messages)) == 30
    assert len(risk_messages) == 30
    assert len(report.top_trades[0].debate_scores) == 30
    assert all("monitoring thresholds" in message for message in risk_messages)
    assert len(report.debate) == 94


def StubProviderSnapshot(symbol: str) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        prices=(100.0, 101.0),
        timestamps=(1_700_000_000, 1_700_086_400),
        source="Test fixture",
    )
