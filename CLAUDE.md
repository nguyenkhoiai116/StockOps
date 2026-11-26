<!-- planfirst:start -->
## Architecture Reference
Full spec: `./docs/architecture.md` — read before adding any infrastructure.

### Stack (momento: validate)
- Backend: Flask monolith, per-feature blueprints in `wms/features/`
- Database: SQLite (`wms.db`, WAL mode), migrations in `wms/migrations/` via PRAGMA user_version
- Frontend: plain HTML/CSS + vanilla JS ES modules in `static/` (existing pages); React + Next.js allowed in `web/` (not created yet), talking to Flask only over `/api/*`
- 3D warehouse: Three.js (pinned version, CDN import map in `static/index.html`), all drawing code in `static/js/wh3d.js`, loaded only when the 3D view opens, falls back to 2D
- Simulators: separate Flask apps in `sims/` (temp_sim :5101, store_sim :5102), HTTP only
- ML: scikit-learn HistGradientBoosting + pandas, trained offline in `ml/`, served via joblib
- Agent: single LLM with tool calling, hand-written loop in `wms/ai/`; LLM called via `requests` to an OpenAI-compatible endpoint (OpenRouter by default) configured by `.env`
- RAG: local sentence-transformers embeddings stored in SQLite, numpy cosine search
- Realtime: polling every 3–5 s

### Agent Rules
- DO NOT add infrastructure that isn't solving a problem you have today.
- KEEP Flask + SQLite as the only backend. DO NOT introduce FastAPI, PostgreSQL, Docker, Redis, Celery, Kafka or MQTT unless a trigger in docs/architecture.md "Thêm Sau" is met.
- React and Next.js (with TypeScript and npm) ARE ALLOWED for the frontend, ONLY inside `web/`. Existing vanilla JS pages in `static/` stay valid; DO NOT rewrite a page unless the user asks for that page.
- Use Next.js as the single React setup. DO NOT add a second React toolchain (Vite, CRA) or another UI framework (Vue, Svelte, Angular) unless the user asks.
- `web/` MUST get and change data only through the Flask API (`/api/*`). Next.js route handlers, server actions and server components MUST NOT open `wms.db`, hold inventory rules or call the LLM.
- Each page MUST live in exactly one frontend. When a page moves to `web/`, remove its vanilla version in the same change.
- In dev, `web/` runs on :3000 and proxies `/api/*` to Flask :5000. In production, build `web/` as a static export served by Flask; DO NOT add a Node server unless the trigger in "Thêm Sau" is met.
- `web/` MUST reuse the design tokens in `static/css/theme.css`; DO NOT create a second palette.
- DO NOT put secrets in `NEXT_PUBLIC_*` variables. COMMIT `package-lock.json`; NEVER commit `node_modules/`, `.next/` or `out/`.
- FOLLOW the per-feature layout: backend blueprint in `wms/features/<name>.py` registered in `wms/__init__.py`; frontend page either in `static/js/features/<name>.js` registered in `static/js/app.js` (vanilla), or in `web/app/<name>/page.tsx` (Next.js).
- PUT all inventory business rules in `wms/core.py`. Every write MUST run inside a transaction via `core.run()` or `with con:`; a `with con:` block that writes MUST call `lock(con)` (`wms/db.py`) as its first statement, before any check it reads.
- NEVER change schema in `seed.py`. ADD a new numbered file in `wms/migrations/` instead.
- Roles and permissions MUST be defined only in `wms/roles.py`; every new `/api/*` route MUST be listed in `PERMS` there (`python -m unittest discover tests` checks this). NEVER commit passwords or password hashes for sample users.
- Login and permission checks live in `guard()` (`wms/features/auth.py`), deny by default. Frontend `can()` only hides buttons; NEVER rely on it for security. Use `can()` for every new action button.
- Simulators in `sims/` MUST NOT import from `wms/` or open `wms.db`. They talk to StockOps only over HTTP (`/api/ingest/*`, `/api/orders`).
- Backfill mode MUST only write `sensor_readings`, `store_traffic`, `store_sales`. It MUST NOT create orders or touch `batches`.
- Agent tools MUST be read-only, except `propose_*` tools which only insert into `agent_actions`. NEVER let the LLM call write endpoints directly.
- Live numbers (stock, alerts, KPI, forecasts) MUST come from tools. RAG (`search_docs`) is ONLY for documents in `knowledge/`.
- DO NOT use LangChain, LlamaIndex, CrewAI, AutoGen or any vector database service.
- ALL LLM calls MUST go through `wms/ai/llm.py`.
- DO NOT let the LLM write free-form SQL.
- Feature engineering MUST live in `ml/features.py` and be shared by training and prediction.
- Every model MUST beat a seasonal-naive baseline on a time-based holdout (last 28 days) before it is served.
- NEVER put API keys in frontend code or commit `.env`.
- PREFER polling (3–5 s) for live views over WebSocket/SSE.
- Write code comments in Vietnamese; keep variable names short and consistent with existing code (`con`, `rows`, `day`, `bad`, `log`).
<!-- planfirst:end -->
