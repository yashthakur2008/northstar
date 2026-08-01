# Northstar — Multi-Agent Hedge Fund Analyzer

An observable public-equity research desk built with FastAPI and a compact,
responsive dashboard. Each request validates live daily market history, runs a
Bull–Bear debate, applies an independent risk haircut, and exposes the Portfolio
Manager verdict as a streamed event sequence.

## Capabilities

- Concurrent analysis for 1–5 validated ticker symbols
- Live, source-labeled daily price history with strict timeouts and provider failover
- Deterministic momentum scoring and realized-volatility adjustment
- Confidence caps and explicit evidence limitations
- Server-Sent Events (SSE) for the live agent room
- Configurable 1–30 round research with distinct rolling windows and risk lenses
- Three-way Bull → Bear rebuttal → Risk adjudication in every round
- Live stage progress and explicit cross-stock conviction ranking
- Interactive, source-attributed 1M/3M price charts with pointer and keyboard inspection
- Seamless, continuously scrolling market tape with center magnification, manual drag/scroll, and line/range-box formats
- Click-through stock details plus an OHLCV Stock Analyzer with 1M–2Y periods, daily/weekly intervals, and line/candlestick views
- Separate, timestamped market-news section with outbound source links, stale-cache protection, and RSS failover
- Context-aware guided Help tour for every major research surface
- Persistent light/dark theme control with first-visit system preference
- Password and optional Google/GitHub OAuth login with HTTP-only sessions
- Account-linked portfolios with provider-refreshed value, session change, and cost-basis return
- Typed contracts, same-origin security defaults, health check, and API docs
- Responsive dashboard with loading, partial-data, and failure states

This is a **screening tool**, not an autonomous trading system. Its current
signal uses market history only. Fundamental, valuation, earnings, news,
options, liquidity, and borrow inputs must be added before treating output as a
full investment pitch. The application states this limitation prominently.

## Architecture

```text
Yahoo chart API → Market Data → Technical signal
                              ↘ Bull ↔ Bear (1–4 rounds)
                                → Risk haircut
                                → Portfolio Manager verdict
                                → SSE stream + typed report
```

`backend/providers.py` owns external data, Yahoo → Nasdaq failover, caching,
and provenance. `backend/engine.py`
owns the deterministic pipeline. `backend/models.py` is the API contract.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --app-dir backend
```

Open <http://localhost:8000>; API docs are at <http://localhost:8000/api/docs>.

## API

- `GET /api/health` — readiness and version
- `POST /api/analyze` — complete JSON report
- `POST /api/analyze/stream` — SSE `status`, `debate`, and `report` events
- `GET /api/market-pulse` — recent stock snapshots, mini-chart history, and current headlines
- `GET /api/stock-analyzer` — validated OHLCV history and derived range, return, volume, and volatility metrics
- `GET /api/portfolio` — authenticated, provider-refreshed portfolio

```json
{"tickers": ["NVDA", "MSFT"], "debate_rounds": 2}
```

The Yahoo Finance adapter and Nasdaq fallback need no key. Set `ALLOWED_ORIGINS` only
for a separately hosted frontend (comma-separated exact origins). Same-origin
deployment intentionally adds no CORS middleware. The service fails closed when
market data is unavailable and issues no synthetic prediction.

## Optional Google and GitHub login

Email/password registration works without external credentials. To enable the
federated buttons on Render, add these environment variables:

```text
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET
```

Register these production callback URLs with the corresponding OAuth apps:

```text
https://hedgefundai.onrender.com/api/auth/oauth/google/callback
https://hedgefundai.onrender.com/api/auth/oauth/github/callback
```

For local OAuth testing, register the equivalent callback on
`http://localhost:8000`. Northstar validates a short-lived state cookie before
exchanging an authorization code and never sends provider tokens to the browser.

## Accuracy posture

The score is one-month return × 3, capped at ±80, then reduced by a volatility
penalty above 20%. Confidence is reduced by volatility and capped at 82%. This
makes the model explainable and reproducible; it does **not** prove future
predictive power. Walk-forward backtesting, a benchmark, survivorship-bias
controls, transaction costs, and independent sources are required before any
claim of investment-grade predictive accuracy.
