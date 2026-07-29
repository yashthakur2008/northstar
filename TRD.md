# Technical Requirements Document: Multi-Agent Hedge Fund Analyzer

**Status:** Draft v1 — Phase 1 (deployable skeleton, mocked agent output)
**Companion doc:** `PRD_Multi-Agent_Hedge_Fund_Analyzer.md`
**Last updated:** July 14, 2026

---

## 1. Scope of this phase

This TRD covers the **walking skeleton**: a real FastAPI backend and a real static frontend, wired together and deployable to Render on day one, with the `/api/analyze` endpoint returning a **mocked** `AnalysisReport` that matches the exact schema the real LangGraph agent pipeline will return in Phase 2. No database. No LLM calls yet. The goal is to de-risk deployment and the frontend/backend contract before building the expensive part.

Everything downstream (LangGraph agents, real data sources, Groq/Gemini calls) plugs into `analyze()` in `main.py` without changing the API contract or the frontend.

---

## 2. Architecture

```
Browser
  │  GET /                 → serves frontend/index.html
  │  POST /api/analyze     → returns AnalysisReport JSON
  ▼
┌─────────────────────────────┐
│  Render Web Service          │
│  (single Python process)     │
│                               │
│  FastAPI app (backend/main.py)│
│   ├── /api/health             │
│   ├── /api/analyze             │
│   └── StaticFiles mount → frontend/
└─────────────────────────────┘
```

**Design decision: one Render service, not two.** The backend serves the static frontend directly via FastAPI's `StaticFiles`, instead of deploying a separate Render static site. This avoids CORS configuration, avoids paying for/managing two services, and means there is exactly one URL and one `render.yaml` service block. Trade-off: if the frontend later grows into a build-step framework (React/Vite), it's easy to split into two services then — this isn't a one-way door.

---

## 3. Repository layout

```
hedge-fund-analyzer/
├── backend/
│   ├── main.py              # FastAPI app, routes, static mount
│   ├── models.py            # Pydantic schemas — the API contract
│   ├── mock_data.py         # Phase 1 mock report generator
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── script.js
├── render.yaml               # Render Blueprint — one command deploy
├── .gitignore
└── README.md
```

No `app/` package nesting yet — flat files, since the surface area is small. Phase 2 will introduce `backend/agents/`, `backend/graph.py`, and `backend/data_sources/` as the LangGraph pipeline is built out; `main.py`'s route bodies are the only thing that changes.

---

## 4. API contract

### `GET /api/health`
Returns `{"status": "ok"}`. Used by Render health checks and uptime pings.

### `POST /api/analyze`

**Request**
```json
{
  "tickers": ["AAPL", "NVDA"],
  "debate_rounds": 2
}
```

| Field | Type | Constraints |
|---|---|---|
| `tickers` | `list[str]` | 1–5 items, required |
| `debate_rounds` | `int` | 1–4, default 2 |

**Response** (`AnalysisReport`)
```json
{
  "top_trades": [
    {
      "symbol": "AAPL",
      "direction": "long",
      "thesis": "...",
      "confidence": 0.74,
      "key_risks": ["...", "..."],
      "supporting_agents": ["News", "Fundamentals"],
      "dissenting_agents": ["Risk"]
    }
  ],
  "market_context": "...",
  "generated_at": "2026-07-14T18:00:00Z",
  "is_mocked": true
}
```

`is_mocked` is a Phase 1–only field so the frontend can visibly flag placeholder data — it will always be `false` once Phase 2 wires in the real pipeline, and can be dropped from the schema at that point.

This contract is defined once in `backend/models.py` and is the single source of truth — the frontend's expectations and the eventual LangGraph judge's output must both conform to it.

---

## 5. Frontend

Plain HTML/CSS/JS, no build step — keeps the "one Render service, no build pipeline" property from Section 2. `script.js` does a single `fetch('/api/analyze', {method: 'POST', ...})` and renders the response. No framework dependency is introduced until there's an actual reason to (e.g., the SSE live-debate view from the PRD's P1 requirements).

---

## 6. Deployment (Render)

- **Service type:** Web Service, Python runtime, free plan.
- **Build command:** `pip install -r backend/requirements.txt`
- **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT --app-dir backend`
- **Health check path:** `/api/health`
- Render injects `$PORT`; the app must bind to it and to `0.0.0.0` (not `127.0.0.1`) or the deploy will fail health checks.
- Defined declaratively in `render.yaml` so the whole service is created from a GitHub push via Render's Blueprint feature — no manual dashboard configuration required.
- **Known free-tier behavior:** service sleeps after 15 minutes idle, ~30–60s cold start on the next request. Acceptable for a demo; call out in the README so it isn't mistaken for a bug.

### Environment variables
None are required for Phase 1 (mocked data needs no API keys). `backend/.env.example` documents the keys Phase 2 will need (`GROQ_API_KEY`, `GEMINI_API_KEY`, `NEWSAPI_KEY`) so the Render dashboard's env var setup can happen ahead of time if desired — they're just unused until `analyze()` is rewritten.

---

## 7. Non-functional requirements (Phase 1)

- **Cold-start correctness:** app must serve `/api/health` successfully within Render's default health-check timeout on a cold start.
- **No secrets in the repo:** `.env` is gitignored; only `.env.example` (no real values) is committed.
- **CORS:** wide open (`allow_origins=["*"]`) since frontend and backend are same-origin in this architecture — kept permissive only because there's currently no cross-origin use case, not because it's been hardened.
- **Schema stability:** `models.py` is the contract Phase 2 must not silently break; any field change here is a breaking change for the frontend.

---

## 8. Explicitly deferred to Phase 2

- LangGraph state machine, the six specialist agents, Bull/Bear debate loop, Portfolio Manager judge.
- Real data sources (yfinance, news API, FRED, options data).
- Groq/Gemini API integration.
- SSE streaming of the live debate.
- Everything in the PRD's Non-Goals (auth, DB, backtesting, brokerage integration) remains out of scope here too.
