"""Resilient market-data adapter with bounded requests and explicit provenance."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
_news_cache: tuple[float, list[dict]] | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    prices: tuple[float, ...]
    timestamps: tuple[int, ...]
    source: str = "Yahoo Finance chart API"

    @property
    def last(self) -> float:
        return self.prices[-1]

    @property
    def change_pct(self) -> float:
        return ((self.prices[-1] / self.prices[-2]) - 1) * 100 if len(self.prices) > 1 else 0.0

    @property
    def return_1m(self) -> float:
        anchor = self.prices[-22] if len(self.prices) >= 22 else self.prices[0]
        return ((self.last / anchor) - 1) * 100

    @property
    def volatility(self) -> float:
        returns = [(self.prices[i] / self.prices[i - 1]) - 1 for i in range(1, len(self.prices))]
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
        return math.sqrt(variance) * math.sqrt(252) * 100

    @property
    def as_of(self) -> datetime:
        return datetime.fromtimestamp(self.timestamps[-1], tz=timezone.utc)


class MarketDataError(RuntimeError):
    def __init__(self, provider: str, symbol: str, reason: str) -> None:
        self.provider = provider
        self.symbol = symbol
        self.reason = reason
        super().__init__(f"{provider} failed for {symbol}: {reason}")


class MarketDataProvider(Protocol):
    async def fetch(self, symbol: str) -> MarketSnapshot: ...


class YahooMarketData:
    def __init__(self, timeout: float = 7.0, cache_ttl: float = 300.0) -> None:
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, MarketSnapshot]] = {}
        self._lock = asyncio.Lock()

    async def fetch(self, symbol: str) -> MarketSnapshot:
        async with self._lock:
            cached = self._cache.get(symbol)
            if cached and time.monotonic() - cached[0] < self.cache_ttl:
                return cached[1]
        snapshot = await asyncio.to_thread(self._fetch_sync, symbol)
        async with self._lock:
            self._cache[symbol] = (time.monotonic(), snapshot)
        return snapshot

    def _fetch_sync(self, symbol: str) -> MarketSnapshot:
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{quote(symbol)}?range=3mo&interval=1d&events=div%2Csplits"
        )
        request = Request(url, headers={"User-Agent": "HedgeFundAnalyzer/1.0"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except HTTPError as exc:
            raise MarketDataError("Yahoo Finance", symbol, f"HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise MarketDataError("Yahoo Finance", symbol, type(exc).__name__) from exc

        try:
            result = payload["chart"]["result"][0]
            raw_prices = result["indicators"]["quote"][0]["close"]
            raw_times = result["timestamp"]
            rows = [(int(ts), float(price)) for ts, price in zip(raw_times, raw_prices) if price is not None]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MarketDataError("Yahoo Finance", symbol, "invalid response") from exc
        if len(rows) < 2:
            raise MarketDataError("Yahoo Finance", symbol, "insufficient history")
        return MarketSnapshot(symbol=symbol, timestamps=tuple(row[0] for row in rows), prices=tuple(row[1] for row in rows))


class NasdaqMarketData:
    """Keyless fallback using Nasdaq's public historical quote endpoint."""

    def __init__(self, timeout: float = 9.0) -> None:
        self.timeout = timeout

    async def fetch(self, symbol: str) -> MarketSnapshot:
        return await asyncio.to_thread(self._fetch_sync, symbol)

    def _fetch_sync(self, symbol: str) -> MarketSnapshot:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=120)
        url = (
            "https://api.nasdaq.com/api/quote/"
            f"{quote(symbol)}/historical?assetclass=stocks&fromdate={start.isoformat()}"
            f"&todate={today.isoformat()}&limit=100"
        )
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; NorthstarResearch/1.0)",
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://www.nasdaq.com/",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except HTTPError as exc:
            raise MarketDataError("Nasdaq", symbol, f"HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise MarketDataError("Nasdaq", symbol, type(exc).__name__) from exc
        try:
            raw_rows = payload["data"]["tradesTable"]["rows"]
            parsed = [
                (
                    int(datetime.strptime(row["date"], "%m/%d/%Y").replace(tzinfo=timezone.utc).timestamp()),
                    float(row["close"].replace("$", "").replace(",", "")),
                )
                for row in raw_rows
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketDataError("Nasdaq", symbol, "invalid response") from exc
        parsed.sort(key=lambda row: row[0])
        if len(parsed) < 2:
            raise MarketDataError("Nasdaq", symbol, "insufficient history")
        return MarketSnapshot(
            symbol=symbol,
            timestamps=tuple(row[0] for row in parsed),
            prices=tuple(row[1] for row in parsed),
            source="Nasdaq historical API",
        )


class ResilientMarketData:
    """Cache results and fail over across independent providers."""

    def __init__(
        self,
        providers: tuple[MarketDataProvider, ...] | None = None,
        cache_ttl: float = 300.0,
    ) -> None:
        self.providers = providers or (YahooMarketData(), NasdaqMarketData())
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, MarketSnapshot]] = {}
        self._lock = asyncio.Lock()

    async def fetch(self, symbol: str) -> MarketSnapshot:
        async with self._lock:
            cached = self._cache.get(symbol)
            if cached and time.monotonic() - cached[0] < self.cache_ttl:
                return cached[1]

        failures: list[str] = []
        for provider in self.providers:
            try:
                snapshot = await provider.fetch(symbol)
            except MarketDataError as exc:
                failures.append(f"{exc.provider}: {exc.reason}")
                logger.warning("market_provider_failed provider=%s symbol=%s reason=%s", exc.provider, symbol, exc.reason)
                continue
            async with self._lock:
                self._cache[symbol] = (time.monotonic(), snapshot)
            logger.info("market_provider_succeeded provider=%s symbol=%s", snapshot.source, symbol)
            return snapshot

        reason = "; ".join(failures) or "no provider returned data"
        logger.error("all_market_providers_failed symbol=%s failures=%s", symbol, reason)
        raise MarketDataError("all providers", symbol, reason)


def fetch_yahoo_news(query: str = "stock market", limit: int = 6, timeout: float = 7.0) -> list[dict]:
    """Fetch source-labeled headlines with RSS and stale-cache failover."""
    global _news_cache
    if _news_cache and time.monotonic() - _news_cache[0] < 300:
        return _news_cache[1][:limit]
    url = (
        "https://query1.finance.yahoo.com/v1/finance/search?"
        f"q={quote(query)}&quotesCount=0&newsCount={max(1, min(limit, 10))}"
    )
    request = Request(url, headers={"User-Agent": "NorthstarResearch/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("news_provider_failed provider=Yahoo Finance reason=%s", type(exc).__name__)
        payload = {}
    items: list[dict] = []
    for item in payload.get("news", []):
        title = item.get("title")
        link = item.get("link")
        published = item.get("providerPublishTime")
        if not title or not link or not published:
            continue
        items.append({
            "title": str(title),
            "publisher": str(item.get("publisher") or "Yahoo Finance"),
            "published_at": datetime.fromtimestamp(int(published), tz=timezone.utc),
            "url": str(link),
        })
    if not items:
        rss_urls = (
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ&region=US&lang=en-US",
            f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en",
        )
        for rss_url in rss_urls:
            try:
                request = Request(rss_url, headers={"User-Agent": "NorthstarResearch/1.0"})
                with urlopen(request, timeout=timeout) as response:
                    root = ET.parse(response).getroot()
                for node in root.findall(".//item"):
                    title = node.findtext("title")
                    link = node.findtext("link")
                    published = node.findtext("pubDate")
                    source = node.findtext("source") or "Market news"
                    if title and link and published:
                        items.append({
                            "title": title,
                            "publisher": source,
                            "published_at": parsedate_to_datetime(published).astimezone(timezone.utc),
                            "url": link,
                        })
                if items:
                    break
            except (HTTPError, URLError, TimeoutError, ET.ParseError, ValueError) as exc:
                logger.warning("news_rss_failed url=%s reason=%s", rss_url, type(exc).__name__)
    if items:
        _news_cache = (time.monotonic(), items[:limit])
        return items[:limit]
    if _news_cache:
        return _news_cache[1][:limit]
    return []


def fetch_yahoo_analysis(symbol: str, period: str, interval: str, timeout: float = 9.0) -> dict:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{quote(symbol)}?range={quote(period)}&interval={quote(interval)}&events=div%2Csplits"
    )
    request = Request(url, headers={"User-Agent": "NorthstarResearch/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise MarketDataError("Yahoo Finance", symbol, f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MarketDataError("Yahoo Finance", symbol, type(exc).__name__) from exc
    try:
        result = payload["chart"]["result"][0]
        quote_rows = result["indicators"]["quote"][0]
        timestamps = result["timestamp"]
        meta = result.get("meta", {})
        rows = []
        for index, timestamp in enumerate(timestamps):
            values = {field: quote_rows.get(field, [None] * len(timestamps))[index] for field in ("open", "high", "low", "close")}
            if any(value is None for value in values.values()):
                continue
            volume = quote_rows.get("volume", [0] * len(timestamps))[index] or 0
            rows.append({
                "timestamp": datetime.fromtimestamp(int(timestamp), tz=timezone.utc),
                **{field: round(float(value), 4) for field, value in values.items()},
                "volume": max(0, int(volume)),
            })
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MarketDataError("Yahoo Finance", symbol, "invalid response") from exc
    if len(rows) < 2:
        raise MarketDataError("Yahoo Finance", symbol, "insufficient history")
    return {
        "symbol": symbol,
        "currency": str(meta.get("currency") or "USD"),
        "rows": rows,
        "source": "Yahoo Finance chart API",
    }
