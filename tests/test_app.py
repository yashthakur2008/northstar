from fastapi.testclient import TestClient

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


def test_request_validation() -> None:
    client = TestClient(app)
    assert client.post("/api/analyze", json={"tickers": ["bad ticker"]}).status_code == 422
    assert client.post("/api/analyze", json={"tickers": ["A", "B", "C", "D", "E", "F"]}).status_code == 422
    assert client.post("/api/analyze", json={"tickers": ["A"], "debate_rounds": 31}).status_code == 422


async def test_engine_is_deterministic_and_traced() -> None:
    report = await AnalysisEngine(StubProvider()).analyze(AnalyzeRequest(tickers=["TEST"], debate_rounds=2))
    assert report.source_status == "live"
    assert report.is_mocked is False
    assert len(report.top_trades) == 1
    assert report.top_trades[0].confidence <= 0.82
    assert len(report.top_trades[0].price_history) == 45
    assert report.top_trades[0].price_history[-1].close == 122.0
    assert report.debate[-1].agent == "Portfolio Manager"
    assert all(item.source for item in report.top_trades[0].evidence)
    round_messages = [event.message for event in report.debate if event.round]
    assert len(round_messages) == 4
    assert len(set(round_messages)) == 4


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
    assert len(bull_messages) == 30
    assert len(set(bull_messages)) == 30
    assert len(report.debate) == 64


def StubProviderSnapshot(symbol: str) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        prices=(100.0, 101.0),
        timestamps=(1_700_000_000, 1_700_086_400),
        source="Test fixture",
    )
