"""Resilient market-data adapter with bounded requests and explicit provenance."""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


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
    pass


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
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise MarketDataError(f"market data unavailable for {symbol}") from exc

        try:
            result = payload["chart"]["result"][0]
            raw_prices = result["indicators"]["quote"][0]["close"]
            raw_times = result["timestamp"]
            rows = [(int(ts), float(price)) for ts, price in zip(raw_times, raw_prices) if price is not None]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MarketDataError(f"invalid market-data response for {symbol}") from exc
        if len(rows) < 2:
            raise MarketDataError(f"insufficient market history for {symbol}")
        return MarketSnapshot(symbol=symbol, timestamps=tuple(row[0] for row in rows), prices=tuple(row[1] for row in rows))
