# Multi-Agent Hedge Fund Analyzer

Phase 1 skeleton: a real FastAPI backend + static frontend, deployable to
Render on day one, with `/api/analyze` returning mocked data shaped exactly
like the real LangGraph agent pipeline will in Phase 2.

See `PRD_Multi-Agent_Hedge_Fund_Analyzer.md` for product scope and
`TRD.md` for the technical architecture.

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --app-dir .
```

Open http://localhost:8000 — the FastAPI app serves the frontend directly,
so there's nothing else to run.

## Deploy to Render

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, point it at the repo. `render.yaml` at
   the root defines the service — no manual configuration needed.
3. First deploy will succeed with no environment variables set (Phase 1
   needs none). Free tier: expect a 30–60s cold start after 15 minutes of
   inactivity — that's Render's free-tier behavior, not a bug.

## Project status

- [x] Phase 1 — deployable skeleton, mocked `/api/analyze`
- [ ] Phase 2 — LangGraph agent pipeline, real data sources, Groq/Gemini
- [ ] Phase 3 — Bull/Bear debate loop + Portfolio Manager judge wired to real data
- [ ] Phase 4 — SSE live-debate streaming in the frontend
- [ ] Phase 5 — polish + disclaimer copy finalized for a public demo link
