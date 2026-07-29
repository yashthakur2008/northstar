"""
Recent headlines via NewsAPI.org's `/v2/everything` endpoint. The free
"Developer" plan is dev/test only -- its terms prohibit staging or
production use, cap requests at 100/day, and delay articles by ~24h -- so
this is fine against a local backend but not licensed for a deployed
Render service. Swap for a paid NewsAPI plan (or a different provider)
before deploying with this key set.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

NEWSAPI_BASE = "https://newsapi.org/v2/everything"
LOOKBACK_DAYS = 7
MAX_HEADLINES = 8


def get_recent_news(symbol: str) -> dict | None:
    api_key = os.environ.get("NEWSAPI_KEY")
    if not api_key:
        return None

    today = datetime.now(timezone.utc).date()
    resp = requests.get(
        NEWSAPI_BASE,
        params={
            "q": symbol,
            "from": (today - timedelta(days=LOOKBACK_DAYS)).isoformat(),
            "to": today.isoformat(),
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": MAX_HEADLINES,
            "apiKey": api_key,
        },
        timeout=10,
    )
    resp.raise_for_status()
    articles = resp.json().get("articles", [])
    if not articles:
        return None

    headlines = [
        {
            "headline": article.get("title"),
            "source": (article.get("source") or {}).get("name"),
            "summary": article.get("description"),
        }
        for article in articles[:MAX_HEADLINES]
    ]
    return {"headlines": headlines}
