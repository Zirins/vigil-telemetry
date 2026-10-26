# Vigil

Vigil ingests application logs and metrics over HTTP in batches, flags anomalies with statistical detectors (z-score spike, error-rate burst, repeated-error pattern), opens incidents automatically, and streams events to a live dashboard over WebSockets. Optional post-incident analysis with Claude (summary, root cause, remediation steps) is off by default; enable it with ENABLE_LIVE_AI_ANALYSIS.

Built with AI coding assistants. Open-incident dedup under concurrent requests is covered by an integration test against real PostgreSQL; detection quality and ingestion throughput are measured by the benchmark scripts below (no broader unit test coverage yet).

## Live Demo

[https://getvigilapp.vercel.app](https://getvigilapp.vercel.app)

The hosted demo is a snapshot of simulated data. No simulator runs continuously, so the dashboard shows Snapshot Mode. To see live streaming, run `python simulator/simulate.py --base-url <your backend URL> --duration 90 --rate 4`.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| Database | PostgreSQL 16 |
| AI | Anthropic Claude API (`claude-sonnet-4-6`) |
| Realtime | Native FastAPI WebSockets |
| Frontend | Next.js 14, TypeScript, TailwindCSS, shadcn/ui, TanStack Query, Recharts |
| Deployment | Railway (backend + Postgres), Vercel (frontend) |

## Build Status

| Component | Status |
|---|---|
| Backend API | **Complete** — models, schemas, services, routers, WebSocket manager, detection, NLP |
| Database schema | **Complete** — five tables via Alembic migration |
| Anomaly detection | **Complete & benchmarked** — see metrics below |
| AI incident analysis | **Complete** — opt-in live via `ENABLE_LIVE_AI_ANALYSIS` or manual backfill via `analyze_one_incident.py` |
| Event simulator | **Complete** — `simulator/simulate.py` |
| Frontend dashboard | **Complete** — services, live streams, incidents, AI reports |
| Benchmark scripts | **Complete** — `backend/scripts/benchmark.py`, `throughput_benchmark.py` |
| Railway deployment | **Complete** — deployed on Railway |
| Vercel deployment | **Complete** — live at [https://getvigilapp.vercel.app](https://getvigilapp.vercel.app) |

## Benchmark Results

Measured locally against PostgreSQL 16 (Docker) and a single uvicorn worker.
Raw logs + exact commands: [`benchmarks/results/`](benchmarks/results/).

### Detection accuracy (`backend/scripts/benchmark.py`)

Method: 5 rounds × 3 repeats, fresh service per round (production open-incident
dedup kept), type-strict matching, 10s window. Two schedules:

| Schedule | Precision | Recall | F1 | Log |
|---|---|---|---|---|
| **Tuning** (original timings) | **100.0%** | **28.6%** | **44.4%** | `detection_both_20261003T214429Z.log` |
| **Held-out** (different timings + magnitudes) | **100.0%** | **42.9%** | **60.0%** | same |

Per `detection_type` (micro-average across 3 repeats):

| Type | Tuning P / R / F1 | Held-out P / R / F1 |
|---|---|---|
| spike | 100% / 33.3% / 50.0% | 100% / 33.3% / 50.0% |
| error_rate | 100% / 50.0% / 66.7% | 100% / 50.0% / 66.7% |
| rage_pattern | 0% / 0% / 0%* | 100% / 50.0% / 66.7% |

\*On the tuning schedule, `rage_pattern` is injected after `error_burst`.
`run_detection` checks error-rate first and returns while the window is still
hot, so rage never runs — detector precedence, not a scoring bug. Held-out
schedules rage first so the type is measurable.

Remaining false negatives are mostly **within-round dedup**: only one open
incident per `(service, detection_type)` is allowed.

### Ingestion throughput (`backend/scripts/throughput_benchmark.py`)

Hardware for this run: Lenovo 83F5, Intel Core Ultra 9 275HX, 31.4 GB RAM,
Postgres + API on the same host, **1** sequential HTTP client.

| Tier | Achieved | P99 latency | Failed batches |
|---|---|---|---|
| 10 events/s | 9.9/s | 17ms | 0 |
| 25 events/s | 24.8/s | 28ms | 0 |
| 50 events/s | 49.6/s | 42ms | 0 |
| 100 events/s | **99.2/s** | **89ms** | 0 |

Single sequential client, local Postgres on one laptop, INFO-level batches (detection lookback queries not exercised): a best-case number, not a capacity claim.

Log: `benchmarks/results/throughput_20261003T221623Z.log`. P99 is
hardware-dependent; re-run before quoting.

## Architecture

```
POST /events  →  event_service  →  PostgreSQL
                      ↓
               detection.run_detection()
                      ↓ (anomaly)
               incident_service.create()
                      ↓
               nlp.analyze_incident()  →  Claude API  →  incidents.ai_* fields (opt-in)
                      ↓
               WebSocket broadcast  →  /ws/{service_id}
                      ↓
               Next.js dashboard  ←  api.ts / ws.ts
```

**Five database tables:** `services`, `events`, `metrics`, `incidents`, `alerts`. AI intelligence lives on `incidents` (`ai_summary`, `ai_root_cause`, `ai_affected_components`, `ai_remediation_steps`, `ai_confidence`, `ai_analyzed_at`) — there is no separate `ai_reports` table.

## Run Locally

### 1. Start PostgreSQL (Docker)

Create the named volume once (data survives container removal):

```bash
docker volume create vigil-postgres-data
```

Start Postgres (exposed on host port **5434**):

```bash
docker run --name vigil-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=vigil \
  -p 5434:5432 \
  -v vigil-postgres-data:/var/lib/postgresql/data \
  -d postgres:16
```

If the container already exists but is stopped: `docker start vigil-postgres`.

To recreate the container while keeping data, remove only the container (not the volume) and rerun the command above.

### 2. Configure environment

Create `backend/.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5434/vigil
# ANTHROPIC_API_KEY only needed if ENABLE_LIVE_AI_ANALYSIS=true or running manual backfill script
ANTHROPIC_API_KEY=
ENABLE_LIVE_AI_ANALYSIS=false
ENVIRONMENT=development
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8001
NEXT_PUBLIC_WS_URL=ws://localhost:8001
```

### 3. Backend

```bash
cd backend
python -m venv venv
.\venv\Scripts\activate          # Windows
# source venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

Health check: `curl http://localhost:8001/health` → `{"status":"ok"}`

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at `http://localhost:3001`.

### 5. Run the simulator

From the project root (backend running):

```bash
python simulator/simulate.py --duration 90 --rate 4
```

Expect **~7–10 incidents** (not hundreds). Incidents are created automatically; post-incident AI analysis is opt-in via `ENABLE_LIVE_AI_ANALYSIS=true` (or runnable per incident via `backend/scripts/analyze_one_incident.py`). The simulator registers `payment-service`, streams normal telemetry, then injects metric spikes, error bursts, and rage patterns.

### 6. Run benchmarks (optional)

```bash
# From repo root; backend must be healthy
python backend/scripts/benchmark.py --base-url http://127.0.0.1:8001 --schedule both --rounds 5 --repeats 3 --log-dir benchmarks/results
python backend/scripts/throughput_benchmark.py --base-url http://127.0.0.1:8001
```

See [`benchmarks/results/COMMANDS.md`](benchmarks/results/COMMANDS.md) for the exact reproduction recipe.

## Running Tests

(after steps 1–3 of Run Locally: Postgres running, backend/.env created, venv activated)

Postgres from step 1 must be running. Run migrations and execute the test suite:

```bash
cd backend
pip install -r requirements-dev.txt
alembic upgrade head
pytest
```

Expect **3 passed** (`tests/test_dedup_concurrency.py` and `tests/test_health.py`).

> [!NOTE]
> The concurrency test needs a real Postgres at `DATABASE_URL`. It dynamically creates and deletes its own test service, and should be pointed at a throwaway DB, not demo data.

## Deploy

### Backend (Railway)

- Root directory: `backend/`
- Builder: Dockerfile (`backend/Dockerfile`)
- Config: `backend/railway.toml`
- Add PostgreSQL plugin; Railway sets `DATABASE_URL` (auto-normalized to `postgresql+asyncpg://` in `config.py`)
- Set `ENVIRONMENT=production`
- (Optional) Set `ENABLE_LIVE_AI_ANALYSIS=true` and `ANTHROPIC_API_KEY` if live Claude analysis is desired
- Set `CORS_ORIGINS=https://getvigilapp.vercel.app` (comma-separated if multiple origins; never `*`)
- Start command runs migrations then uvicorn:

```sh
sh -c 'alembic upgrade head; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'
```

### Frontend (Vercel)

- Root directory: `frontend/`
- Set production env vars:

```env
NEXT_PUBLIC_API_URL=https://your-railway-backend.up.railway.app
NEXT_PUBLIC_WS_URL=wss://your-railway-backend.up.railway.app
```

### Seed production demo

```bash
python simulator/simulate.py --base-url https://your-railway-backend.up.railway.app --duration 90 --rate 4
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET/POST | `/services` | List / register services |
| GET | `/services/{id}` | Service detail (recent events, active incidents) |
| PATCH | `/services/{id}/status` | Update service status |
| POST | `/events` | Batch event ingestion |
| GET | `/events/{service_id}` | Paginated event list |
| GET | `/metrics/{service_id}` | Metric history |
| GET | `/metrics/{service_id}/recent` | Recent metrics by name |
| GET | `/incidents` | List / filter incidents |
| GET | `/incidents/{id}` | Incident detail with AI report |
| POST | `/incidents/{id}/resolve` | Resolve incident (optional postmortem) |
| WS | `/ws/{service_id}` | Real-time event stream (`{"type":"event","data":{...}}`) |

## Frontend Pages

| Route | Description |
|---|---|
| `/` | Services overview — status badges, open incident counts, 10s polling |
| `/services/[id]` | Live event stream (WebSocket), metric chart (cpu_pct, error_rate), incident banner |
| `/incidents` | Incident list with status filter |
| `/incidents/[id]` | AI report panel, event timeline, resolve button |

All HTTP traffic goes through `frontend/src/lib/api.ts`; WebSocket through `frontend/src/lib/ws.ts`.

## Project Structure

```
vigil-telemetry/
├── backend/
│   ├── app/                     # FastAPI application
│   ├── alembic/                 # Database migrations
│   ├── scripts/
│   │   ├── benchmark.py         # Detection accuracy benchmark
│   │   └── throughput_benchmark.py
│   ├── tests/                   # Pytest suite (concurrency dedup, health)
│   ├── Dockerfile
│   └── railway.toml
├── benchmarks/
│   └── results/                 # Benchmark results, commands, hardware specs
├── frontend/
│   └── src/
│       ├── app/                 # Next.js App Router pages
│       ├── components/          # ServiceCard, EventStream, MetricChart, AIReport, …
│       ├── lib/                 # api.ts, ws.ts
│       └── types/
├── simulator/
│   └── simulate.py
└── docs/
    └── screenshots/             # UI screenshots
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL URL (`postgresql+asyncpg://...` locally; Railway `postgres://` auto-converted) |
| `ANTHROPIC_API_KEY` | Optional | Anthropic API key for incident AI analysis (only needed when `ENABLE_LIVE_AI_ANALYSIS=true` or running manual backfill script) |
| `ENABLE_LIVE_AI_ANALYSIS` | No | Default: `false`. Opt-in flag to run live async Claude analysis upon incident creation |
| `ENVIRONMENT` | No | Default: `development` (enables SQL echo) |
| `CORS_ORIGINS` | No | Comma-separated allowed frontend origins (default `http://localhost:3000,http://localhost:3001`); never `*` |
| `NEXT_PUBLIC_API_URL` | Frontend | Backend HTTP base URL |
| `NEXT_PUBLIC_WS_URL` | Frontend | Backend WebSocket base URL (`ws://` or `wss://`) |

All backend config is loaded through `backend/app/config.py` — never use inline `os.getenv()` elsewhere.

## Troubleshooting

**`ai_summary` is null after an incident**

1. AI analysis is opt-in — ensure `ENABLE_LIVE_AI_ANALYSIS=true` is set (otherwise run `python backend/scripts/analyze_one_incident.py <id> --confirm`)
2. Full uvicorn restart (stop + start, not just `--reload`)
3. Check logs: if enabled, verify `Scheduled AI analysis task` and `Completed AI analysis`; if disabled, logs show `Skipping live AI analysis`
4. When enabled, verify `ANTHROPIC_API_KEY` is valid and model is `claude-sonnet-4-6`

**Too many incidents from simulator**

Open-incident dedup allows at most one open incident per
`(service_id, detection_type)` (partial unique index). Expect a small number
of open incidents per service while anomalies share those types — not hundreds.

**Railway healthcheck timeout**

Ensure start command uses `;` not `&&` between alembic and uvicorn so uvicorn starts even when migrations are already at head.
