"""FastAPI entrypoint for the multi-agent research desk."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
import httpx
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth import AuthStore, SESSION_SECONDS
from engine import AnalysisEngine
from models import AnalysisReport, AnalyzeRequest, AnalyzerPoint, MarketPulse, NewsItem, Portfolio, PortfolioHolding, PortfolioHoldingInput, PricePoint, StockAnalysis, StockPulse
from providers import MarketDataError, fetch_resilient_analysis, fetch_yahoo_news

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
engine = AnalysisEngine()
auth_store = AuthStore(Path(os.getenv("AUTH_DB_PATH", BASE_DIR / "northstar_auth.db")))
SESSION_COOKIE = "northstar_session"
OAUTH_STATE_COOKIE = "northstar_oauth_state"
OAUTH_NEXT_COOKIE = "northstar_oauth_next"
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
    if request.url.path in {
        "/", "/index.html", "/news.html", "/beginners.html", "/login.html", "/research.html",
        "/style.css", "/script.js", "/news.js", "/site-shell.js", "/auth.js", "/research.js",
    }:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version, "market_data": "Yahoo Finance with Nasdaq fallback"}


class RegisterRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=50)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return normalized


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    secure_cookie = (
        request.url.scheme == "https"
        or bool(os.getenv("RENDER"))
        or os.getenv("COOKIE_SECURE", "").lower() == "true"
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )

def oauth_settings(provider: str) -> tuple[str, str] | None:
    key = provider.upper()
    client_id = os.getenv(f"{key}_CLIENT_ID", "").strip()
    client_secret = os.getenv(f"{key}_CLIENT_SECRET", "").strip()
    return (client_id, client_secret) if client_id and client_secret else None


def secure_request_cookie(request: Request) -> bool:
    return request.url.scheme == "https" or bool(os.getenv("RENDER")) or os.getenv("COOKIE_SECURE", "").lower() == "true"

def require_user(session_token: str | None) -> dict:
    user = auth_store.user_for_session(session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Log in to manage a live portfolio.")
    return user


async def build_portfolio(user_id: int) -> Portfolio:
    saved = auth_store.portfolio_holdings(user_id)
    if not saved:
        return Portfolio(
            holdings=[],
            total_value=0,
            day_change_value=0,
            total_return_value=None,
            generated_at=datetime.now(timezone.utc),
            source_status="live",
        )
    snapshots = await asyncio.gather(
        *(engine.provider.fetch(row["symbol"]) for row in saved),
        return_exceptions=True,
    )
    holdings: list[PortfolioHolding] = []
    failures = 0
    for saved_row, snapshot in zip(saved, snapshots):
        if isinstance(snapshot, Exception):
            failures += 1
            continue
        shares = float(saved_row["shares"])
        average_cost = saved_row["average_cost"]
        market_value = shares * snapshot.last
        previous_close = snapshot.prices[-2] if len(snapshot.prices) > 1 else snapshot.last
        total_return_value = None if average_cost is None else market_value - shares * float(average_cost)
        holdings.append(PortfolioHolding(
            symbol=snapshot.symbol,
            shares=shares,
            average_cost=average_cost,
            last_price=round(snapshot.last, 2),
            market_value=round(market_value, 2),
            day_change_pct=round(snapshot.change_pct, 2),
            day_change_value=round(shares * (snapshot.last - previous_close), 2),
            total_return_pct=None if average_cost is None else round((snapshot.last / float(average_cost) - 1) * 100, 2),
            total_return_value=None if total_return_value is None else round(total_return_value, 2),
            as_of=snapshot.as_of,
            source=snapshot.source,
        ))
    known_returns = [row.total_return_value for row in holdings if row.total_return_value is not None]
    invested_value = sum(
        row.shares * float(row.average_cost)
        for row in holdings
        if row.average_cost is not None
    )
    history = []
    successful = [
        (saved_row, snapshot)
        for saved_row, snapshot in zip(saved, snapshots)
        if not isinstance(snapshot, Exception)
    ]
    if successful:
        common_timestamps = set(successful[0][1].timestamps[-64:])
        for _, snapshot in successful[1:]:
            common_timestamps &= set(snapshot.timestamps[-64:])
        price_maps = [
            (float(saved_row["shares"]), dict(zip(snapshot.timestamps, snapshot.prices)))
            for saved_row, snapshot in successful
        ]
        history = [
            {
                "timestamp": datetime.fromtimestamp(timestamp, tz=timezone.utc),
                "value": round(sum(shares * prices[timestamp] for shares, prices in price_maps), 2),
            }
            for timestamp in sorted(common_timestamps)
        ]
    history_returns = [
        history[index]["value"] / history[index - 1]["value"] - 1
        for index in range(1, len(history))
        if history[index - 1]["value"] > 0
    ]
    portfolio_volatility = None
    if len(history_returns) > 1:
        mean_return = sum(history_returns) / len(history_returns)
        variance = sum((value - mean_return) ** 2 for value in history_returns) / (len(history_returns) - 1)
        portfolio_volatility = round(math.sqrt(variance) * math.sqrt(252) * 100, 2)
    contributor_values = [
        (row.symbol, row.total_return_value if row.total_return_value is not None else row.day_change_value)
        for row in holdings
    ]
    return Portfolio(
        holdings=holdings,
        total_value=round(sum(row.market_value for row in holdings), 2),
        day_change_value=round(sum(row.day_change_value for row in holdings), 2),
        total_return_value=round(sum(known_returns), 2) if known_returns else None,
        total_return_pct=round(sum(known_returns) / invested_value * 100, 2) if known_returns and invested_value else None,
        invested_value=round(invested_value, 2) if invested_value else None,
        volatility=portfolio_volatility,
        best_contributor=max(contributor_values, key=lambda row: row[1])[0] if contributor_values else None,
        worst_contributor=min(contributor_values, key=lambda row: row[1])[0] if contributor_values else None,
        history=history,
        generated_at=datetime.now(timezone.utc),
        source_status="unavailable" if not holdings else "partial" if failures else "live",
    )


@app.post("/api/auth/register", status_code=201)
async def register(payload: RegisterRequest, request: Request, response: Response) -> dict:
    email = normalize_email(payload.email)
    display_name = " ".join(payload.display_name.strip().split())
    try:
        user = auth_store.create_user(email, display_name, payload.password)
    except ValueError as error:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from error
    token = auth_store.create_session(user["id"])
    set_session_cookie(response, request, token)
    return {"authenticated": True, "user": user}


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    user = auth_store.authenticate(normalize_email(payload.email), payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    token = auth_store.create_session(user["id"])
    set_session_cookie(response, request, token)
    return {"authenticated": True, "user": user}


@app.get("/api/auth/me")
async def current_user(northstar_session: str | None = Cookie(default=None)) -> dict:
    user = auth_store.user_for_session(northstar_session)
    return {"authenticated": user is not None, "user": user}


@app.post("/api/auth/logout")
async def logout(response: Response, northstar_session: str | None = Cookie(default=None)) -> dict:
    auth_store.delete_session(northstar_session)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    return {"authenticated": False}


@app.get("/api/auth/providers")
async def auth_providers() -> dict:
    return {"google": oauth_settings("google") is not None, "github": oauth_settings("github") is not None}


@app.get("/api/auth/oauth/{provider}")
async def oauth_start(provider: Literal["google", "github"], request: Request, next: str = "/") -> RedirectResponse:
    settings = oauth_settings(provider)
    if settings is None:
        return RedirectResponse(f"/login.html?oauth_error={provider}_not_configured", status_code=303)
    client_id, _ = settings
    state = secrets.token_urlsafe(32)
    callback = str(request.url_for("oauth_callback", provider=provider))
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    if provider == "google":
        url = httpx.URL("https://accounts.google.com/o/oauth2/v2/auth", params={
            "client_id": client_id, "redirect_uri": callback, "response_type": "code",
            "scope": "openid email profile", "state": state, "prompt": "select_account",
        })
    else:
        url = httpx.URL("https://github.com/login/oauth/authorize", params={
            "client_id": client_id, "redirect_uri": callback, "scope": "read:user user:email", "state": state,
        })
    response = RedirectResponse(str(url), status_code=303)
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, secure=secure_request_cookie(request), samesite="lax")
    response.set_cookie(OAUTH_NEXT_COOKIE, safe_next, max_age=600, httponly=True, secure=secure_request_cookie(request), samesite="lax")
    return response


@app.get("/api/auth/oauth/{provider}/callback", name="oauth_callback")
async def oauth_callback(
    provider: Literal["google", "github"],
    request: Request,
    code: str = Query(min_length=3),
    state: str = Query(min_length=10),
    northstar_oauth_state: str | None = Cookie(default=None),
    northstar_oauth_next: str | None = Cookie(default="/"),
) -> RedirectResponse:
    settings = oauth_settings(provider)
    if settings is None or not northstar_oauth_state or not secrets.compare_digest(state, northstar_oauth_state):
        return RedirectResponse("/login.html?oauth_error=invalid_state", status_code=303)
    client_id, client_secret = settings
    callback = str(request.url_for("oauth_callback", provider=provider))
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            if provider == "google":
                token_response = await client.post("https://oauth2.googleapis.com/token", data={
                    "client_id": client_id, "client_secret": client_secret, "code": code,
                    "grant_type": "authorization_code", "redirect_uri": callback,
                })
                token_response.raise_for_status()
                token = token_response.json()["access_token"]
                profile_response = await client.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {token}"})
                profile_response.raise_for_status()
                profile = profile_response.json()
                provider_id, email, name = str(profile["sub"]), profile["email"], profile.get("name") or profile["email"].split("@")[0]
            else:
                token_response = await client.post("https://github.com/login/oauth/access_token", data={
                    "client_id": client_id, "client_secret": client_secret, "code": code, "redirect_uri": callback,
                }, headers={"Accept": "application/json"})
                token_response.raise_for_status()
                token = token_response.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
                profile_response = await client.get("https://api.github.com/user", headers=headers)
                profile_response.raise_for_status()
                profile = profile_response.json()
                email = profile.get("email")
                if not email:
                    emails_response = await client.get("https://api.github.com/user/emails", headers=headers)
                    emails_response.raise_for_status()
                    emails = emails_response.json()
                    selected = next((item for item in emails if item.get("primary") and item.get("verified")), None)
                    email = selected["email"] if selected else None
                if not email:
                    raise ValueError("A verified GitHub email is required.")
                provider_id, name = str(profile["id"]), profile.get("name") or profile.get("login") or email.split("@")[0]
        user = auth_store.oauth_user(provider, provider_id, normalize_email(email), " ".join(name.strip().split()))
    except (httpx.HTTPError, KeyError, ValueError):
        return RedirectResponse(f"/login.html?oauth_error={provider}_failed", status_code=303)
    destination = northstar_oauth_next if northstar_oauth_next and northstar_oauth_next.startswith("/") and not northstar_oauth_next.startswith("//") else "/"
    response = RedirectResponse(destination, status_code=303)
    set_session_cookie(response, request, auth_store.create_session(user["id"]))
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(OAUTH_NEXT_COOKIE, path="/")
    return response


@app.get("/api/portfolio", response_model=Portfolio)
async def get_portfolio(northstar_session: str | None = Cookie(default=None)) -> Portfolio:
    return await build_portfolio(require_user(northstar_session)["id"])


@app.post("/api/portfolio/holdings", response_model=Portfolio)
async def save_portfolio_holding(
    payload: PortfolioHoldingInput,
    northstar_session: str | None = Cookie(default=None),
) -> Portfolio:
    user = require_user(northstar_session)
    existing = auth_store.portfolio_holdings(user["id"])
    if payload.symbol not in {row["symbol"] for row in existing} and len(existing) >= 20:
        raise HTTPException(status_code=422, detail="A portfolio can contain up to 20 holdings.")
    auth_store.upsert_holding(user["id"], payload.symbol, payload.shares, payload.average_cost)
    return await build_portfolio(user["id"])


@app.delete("/api/portfolio/holdings/{symbol}", response_model=Portfolio)
async def remove_portfolio_holding(
    symbol: str,
    northstar_session: str | None = Cookie(default=None),
) -> Portfolio:
    user = require_user(northstar_session)
    normalized = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", normalized):
        raise HTTPException(status_code=422, detail="Enter a valid ticker symbol.")
    auth_store.delete_holding(user["id"], normalized)
    return await build_portfolio(user["id"])


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
        asyncio.to_thread(fetch_yahoo_news, "stock market", 10),
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
