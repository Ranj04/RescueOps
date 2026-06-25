# RescueOps

**A resilient, self-evaluating AI incident first responder** — built for the Capgemini AIE × CrewAI hackathon, judged on production-readiness.

A CrewAI crew of five specialist agents responds to a simulated production incident end-to-end — classify severity, diagnose root cause with cited evidence, propose fixes split by risk, auto-apply the safe ones, gate the destructive ones behind human approval, verify recovery, and write the postmortem — exposed through a **FastAPI** backend and a **React** console.

See [`KICKOFF-TRANSCRIPT.md`](KICKOFF-TRANSCRIPT.md) for the verbatim kickoff transcript (agenda, TrueFoundry/CrewAI talks, rules, judging criteria, prizes).
See [`TRUEFOUNDRY.md`](TRUEFOUNDRY.md) for how RescueOps routes LLM calls through the TrueFoundry AI Gateway (config, failover, proof of connectivity).
See [`CREWAI-USAGE.md`](CREWAI-USAGE.md) for how RescueOps uses CrewAI (agents, crews, structured output).
See [`CREWAI-DOCS.md`](CREWAI-DOCS.md) for a comprehensive CrewAI reference.

---

## Overview

Production incidents are time-critical and cognitively overloaded. RescueOps deploys five specialist CrewAI agents that run an incident to resolution in one request/response cycle, with **progressive autonomy**: the system acts on its own when it safely can, and stops for a human only when an action is genuinely destructive.

Every LLM call routes through the **TrueFoundry AI Gateway** (Grok primary; Claude and Gemini configured as fallbacks). No agent talks to a model directly — the gateway owns routing and failover. (For local development, the app also supports a direct-Anthropic mode; see [Setup](#setup).)

**The two demo moments that win this hackathon:**

1. **Chaos injection.** A judge breaks a telemetry source (or the primary model) mid-incident from the Chaos Console. The system keeps running, but `DiagnosisReport.confidence` drops for a computed, auditable reason — fewer telemetry signals available, not an LLM guessing lower.

2. **Eval dashboard.** The Eval tab runs `evaluate_all()`, scores the system against all five labeled incidents, and displays accuracy metrics. Judges see measured performance, not vibes.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 + Vite 5 (vanilla JSX, no UI framework) |
| **Backend / API** | FastAPI + Uvicorn (request/response JSON API under `/api`) |
| **Agents** | CrewAI (`Process.sequential` crews) + LiteLLM |
| **LLM routing** | TrueFoundry AI Gateway (Grok primary → Claude / Gemini fallbacks); direct-Anthropic mode for local dev |
| **Observability** | Traceloop SDK → TrueFoundry tracing (best-effort, never blocks a run) |
| **Persistence** | SQLite (`rescueops_audit.db`) — audit event log + eval results |
| **Data** | `incidents.json` — 5 synthetic labeled incidents; no real cloud integrations |
| **Voice (optional)** | xAI Grok TTS with macOS `say` fallback (`voice.py`) |
| **Packaging / deploy** | Single Docker image (multi-stage: Vite build → Python runtime); Railway / Procfile |

The whole app ships as **one container, one URL, no CORS**: FastAPI serves the JSON API under `/api` and the built React bundle (`frontend/dist`) at `/`.

---

## Architecture

```
        ┌──────────────────────────────────────────────────────────┐
        │                   React + Vite SPA (frontend/)            │
        │   Incident Picker │ Chaos Console │ Timeline │ Eval Tab   │
        └───────────────┬───────────────────────────┬──────────────┘
                        │ fetch /api/...             │ Approve / Deny
                        ▼                            ▼
        ┌──────────────────────────────────────────────────────────┐
        │              FastAPI backend (api/server.py)              │
        │   POST /api/runs              → run to approval/resolved  │
        │   POST /api/runs/{id}/approve → resume to resolved        │
        │   GET/POST /api/eval, /api/incidents, /api/health         │
        │   In-memory run-state keyed by run_id                     │
        └───────────────┬──────────────────────────────────────────┘
                        │
                        ▼
        ┌──────────────────────────────────────────────────────────┐
        │                  pipeline.py  (two phases)                │
        │                                                          │
        │  run_until_approval(incident_id, chaos_config)           │
        │    └─ chaos.apply_chaos()  ◄─ degrade observable first   │
        │    └─ _compute_confidence()◄─ deterministic, not LLM     │
        │    └─ [1] Triage  → [2] Diagnosis  (one seq. crew)       │
        │    └─ [3] Remediation → safe[] + risky[]                  │
        │    └─ auto-execute every safe action  (the autonomy)     │
        │         ├─ risky[] empty  → resolve autonomously ──┐     │
        │         └─ risky[] present→ status=awaiting_approval│     │
        │                                                    │     │
        │  resume_after_approval(result, decision) ◄─ human ─┘     │
        │    └─ execute approved risky actions                     │
        │    └─ [4] Verification → [5] Postmortem                   │
        │                                                          │
        │  All agents: config.build_llm() → TrueFoundry Gateway    │
        └───────────────┬──────────────────────────────────────────┘
                        │ per-stage
                        ▼
        ┌─────────────────────────────┐   ┌──────────────────────────┐
        │   audit.log_event()         │   │  evaluation.evaluate_all()│
        │   SQLite: events            │   │  scores vs ground_truth   │
        │   every stage written       │   │  (eval harness only)      │
        └─────────────────────────────┘   └──────────────────────────┘
```

### Two-phase request/response

The backend never blocks an HTTP request on a human. The pipeline is split so a run can pause cleanly between requests:

- **`POST /api/runs`** → `run_until_approval()` runs triage → diagnosis → remediation, **auto-executes every safe action**, then either:
  - **resolves autonomously** (`status: "resolved"`) when remediation produced no risky actions — verification + postmortem run in the same response; or
  - **pauses** (`status: "awaiting_approval"`) with the pending risky actions surfaced. The `RunResult` is held in memory keyed by `run_id`.
- **`POST /api/runs/{run_id}/approve`** → `resume_after_approval()` applies the human decision, executes approved risky actions, then runs verification → postmortem and returns the resolved `RunResult`.

A server restart loses in-flight (paused) runs but never the recorded history — every stage is written to SQLite as it happens.

---

## Repo Map

| Path | Purpose |
|---|---|
| **Backend / pipeline** | |
| `api/server.py` | FastAPI app — `/api` routes + serves the built React bundle at `/` |
| `pipeline.py` | `run_until_approval()`, `resume_after_approval()`, `run_incident()` — orchestrates the crews with progressive autonomy |
| `agents.py` | The 5 CrewAI agent factories (triage, diagnosis, remediation, verification, postmortem) |
| `schemas.py` | All Pydantic artifact types — the integration contract (`RunResult`, etc.) |
| `config.py` | `build_llm()` — routes every agent through TrueFoundry (or direct Anthropic); initializes tracing |
| `incidents.py` / `incidents.json` | `load_incidents()`, `get_incident()`, `observable()` + 5 labeled incidents |
| `audit.py` | SQLite event log — `init_db`, `log_event`, `get_run` |
| `chaos.py` | `apply_chaos()` — degrades the observable before any agent sees it |
| `evaluation.py` | `evaluate_all()`, `get_latest_eval()` — scores all 5 incidents vs `ground_truth` |
| `voice.py` | Optional spoken approval prompt (xAI TTS → macOS `say` fallback) |
| `main.py` | CLI runner — `python main.py --incident <id> [--auto-approve]` |
| **Frontend** | |
| `frontend/src/App.jsx` | Top-level React app — pipeline lifecycle (`idle → running → awaiting_approval → resuming → done`) |
| `frontend/src/components.jsx` | Panels: incident picker, chaos console, artifact panels, approval bar, eval dashboard |
| `frontend/src/api.js` | Thin `fetch` wrapper over the `/api` backend |
| `frontend/vite.config.js` | Vite dev server; proxies `/api` → `:8000` |
| **Deploy** | |
| `Dockerfile` | Multi-stage: build React → Python runtime serving both |
| `dev.sh` | Run backend (`:8000`) + Vite dev server (`:5173`) together |
| `railway.json` / `Procfile` | Railway / PaaS single-service deploy config |
| `requirements.txt` | Python dependencies |
| `.env.example` | Gateway URL, API key, model IDs (copy to `.env`) |

> `app.py` (Streamlit) and the `rescueops/` package are earlier prototypes retained for reference; the live demo is the React + FastAPI stack above.

---

## Progressive Autonomy

The core behavior after remediation produces `safe[]` and `risky[]`:

1. **Every safe action auto-executes** — no human in the loop. That's the autonomy. ("Executing" is simulated: actions are recorded to the audit trail, since there are no real cloud integrations.)
2. **If `risky[]` is empty** → continue straight to verification + postmortem and return a **resolved** result with no pause. Fully autonomous.
3. **If `risky[]` is non-empty** → stop and surface those actions for a human approve/deny decision. That's the governance.

`RunResult.status` is `"awaiting_approval"` or `"resolved"`; `executed_safe` lists the safe actions already applied. The remediation agent is explicitly instructed never to manufacture risky actions to look thorough — so the autonomous path is the common case, and the human gate fires only when a fix genuinely requires a destructive step.

---

## API Reference

All routes are prefixed `/api`.

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Liveness probe |
| `GET /api/incidents` | Selectable incidents (never exposes `ground_truth`) |
| `POST /api/runs` | Run to approval; auto-executes safe actions. Returns `resolved` (no risky) or `awaiting_approval` |
| `POST /api/runs/{run_id}/approve` | Apply the human decision, then verify → postmortem; returns resolved `RunResult` |
| `GET /api/runs/{run_id}` | Fetch the current `RunResult` for a run |
| `GET /api/eval` | Latest persisted eval summary (or `null`) |
| `POST /api/eval` | Run `evaluate_all()` over all 5 incidents; persist + return the summary |

`POST /api/runs` body: `{ "incident_id": str, "chaos_config": { "disable_sources": [...], "break_primary_model": bool } | null }`.
`POST /api/runs/{id}/approve` body: `{ "approved": bool, "approver": str, "note": str }`.

---

## Confidence vs Evaluation

These two concepts are **intentionally separate**. Conflating them would mislead judges about system integrity.

### Runtime confidence (`DiagnosisReport.confidence`)

- Computed **by the pipeline** (`_compute_confidence` in `pipeline.py`), not by the agent's LLM.
- Computed **from the observable only** — the same data slice the agents see.
- Formula: start at `1.0`, subtract a fixed weight per missing/disabled telemetry source:

  | Source disabled | Weight |
  |---|---|
  | `logs` | −0.30 |
  | `metrics` | −0.40 |
  | `deploys` | −0.20 |

- Floor `0.10`; when a judge disables a source, confidence drops mechanically and auditably. **The agent never outputs a confidence number** — the pipeline overrides whatever the LLM returns with the deterministic value.

### Eval-time scoring (`evaluation.py`)

- **Only the eval harness reads `ground_truth`.** Agents, the pipeline, chaos, and the UI never see it (enforced by `incidents.observable()`).
- `severity_correct` = `triage.severity == ground_truth.severity`.
- `evidence_recall` / `remediation_overlap` = fraction of expected items each covered by a produced item, via a directional fuzzy word-coverage matcher (handles short canonical labels vs verbose produced text).

**If a judge asks:** confidence is a real-time signal from telemetry availability; eval accuracy is a post-hoc measurement against labeled ground truth. They measure different things.

---

## Setup

### Requirements

- Python 3.12
- Node 20 (for the React frontend)
- TrueFoundry AI Gateway access (URL + API key) — *or* an `ANTHROPIC_API_KEY` for local direct mode

### Environment

Copy `.env.example` to `.env` and fill in your values:

```
# TrueFoundry gateway mode (production)
TFY_GATEWAY_BASE_URL=https://<your-gateway>.truefoundry.cloud/api/llm
TFY_API_KEY=<your-api-key>
GROK_MODEL_ID=<grok-model-id-as-aliased-in-gateway>
CLAUDE_MODEL_ID=<claude-model-id-as-aliased-in-gateway>
GEMINI_MODEL_ID=<gemini-model-id-as-aliased-in-gateway>
```

Model IDs must match the aliases configured in the TrueFoundry gateway, not raw vendor IDs. For local development, set `ANTHROPIC_API_KEY` instead and leave the gateway URL as the placeholder — `build_llm()` auto-detects the mode.

### Run locally (dev)

```bash
# Backend + frontend together (backend :8000, Vite :5173, /api proxied):
./dev.sh
```

Or run each side manually:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.server:app --reload --port 8000      # backend

cd frontend && npm install && npm run dev          # frontend on :5173
```

Open the Vite dev server (http://localhost:5173) — it proxies `/api` to the backend.

### CLI (no UI)

```bash
python main.py --incident INC-001-checkout-db-pool   # interactive approval
python main.py --incident INC-003-redis-cache-outage --auto-approve
```

### Production / single-service

```bash
docker build -t rescueops .
docker run -p 8000:8000 --env-file .env rescueops
# FastAPI serves the API at /api and the built React app at /
```

`railway.json` and `Procfile` deploy the same image on Railway (health check at `/api/health`).

---

## Demo Script

**Beat 1 — Live incident**
Open the React console. Pick `INC-001-checkout-db-pool`, click **Run incident**. The timeline fills in: `TriageReport` → `DiagnosisReport` (confidence `1.0`, evidence cited) → `RemediationPlan` (safe actions auto-applied, risky flagged).

**Beat 2 — Progressive autonomy + approval gate**
- If remediation produced **no risky action**, the run **resolves autonomously** — verification and postmortem appear with no human gate. Point out: the system acted on its own because every fix was safe.
- If there's a risky action (e.g. "Roll back deploy checkout-v42"), the UI pauses at the **approval bar**. Click **Approve** or **Deny**. The pipeline resumes: `VerificationReport` shows the recovery metric vs threshold; `PostmortemReport` appears.

**Beat 3 — Chaos injection**
Open the **Chaos Console**, disable `metrics`, re-run the incident. `DiagnosisReport.confidence` drops (e.g. to `0.60`) and the UI shows it — a computed drop, not an LLM guess. Optionally enable `break_primary_model`: the gateway routes to the Claude fallback, visible in TrueFoundry traces.

**Beat 4 — Eval dashboard**
Switch to the **Eval** tab, click **Run evaluation**. `evaluate_all()` scores all 5 incidents; the table shows per-incident severity accuracy, evidence recall, remediation overlap, recovery rate, plus aggregates.

---

## Hard Constraints

| Constraint | Rationale |
|---|---|
| No real cloud integrations | All data synthetic (`incidents.json`); action execution is simulated/audited |
| No custom model router | TrueFoundry gateway owns fallback logic; we only call `build_llm()` |
| SQLite, not ClickHouse/Postgres | One file, zero infra, runs anywhere |
| `Process.sequential` crews | No parallel agents, no subcrews — deterministic stage order |
| No auth or user registry | Demo-only; single-user session |
| Agents never see `ground_truth` | Enforced by `incidents.observable()` — agents get only `alert` + `telemetry` |
| Confidence computed, not inferred | The pipeline fills `DiagnosisReport.confidence`; no LLM decides the number |
| Backend never blocks on a human | Two-phase request/response; run-state held in memory keyed by `run_id` |
