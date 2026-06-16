# RescueOps

**A resilient, self-evaluating AI incident first responder** — built for Capgemini AIE × CrewAI hackathon, judged on production-readiness.

---

## Overview

Production incidents are time-critical and cognitively overloaded. RescueOps deploys a CrewAI crew of five specialist agents that respond to a simulated incident end-to-end: classify severity, diagnose root cause with cited evidence, propose fixes sorted by risk, gate destructive actions behind human approval, verify recovery, and write the postmortem — all in under two minutes.

Every LLM call routes through the **TrueFoundry AI Gateway** (Grok primary; Claude and Gemini configured as fallbacks). No agent talks to a model directly; the gateway owns all routing and failover.

**The two demo moments that win this hackathon:**

1. **Chaos injection.** A judge breaks a telemetry source (or the primary model) mid-incident using the Chaos Console. The system continues running, but `DiagnosisReport.confidence` drops for a computed, auditable reason — because fewer telemetry signals are available, not because an LLM guessed lower.

2. **Eval dashboard.** After the live demo, the Eval tab runs `evaluate_all()`, scores the system against all five labeled incidents, and displays accuracy metrics. Judges see measured performance, not vibes.

---

## Architecture

```
                         ┌─────────────────────────────────────────────────┐
                         │                  Streamlit UI (app.py)          │
                         │  Incident Picker │ Artifact Viewer │ Chaos Console │ Eval Dashboard │
                         └────────┬─────────────────────┬───────────────────┘
                                  │                     │ approval button / auto-approve
                                  ▼                     ▼
                         pipeline.run_incident(incident_id, chaos_config, approval_callback)
                                  │
                    ┌─────────────▼──────────────┐
                    │     chaos.apply_chaos()     │  ◄─ strips telemetry sources or flags
                    │  (wraps observable data)    │     model degraded before agents see data
                    └─────────────┬──────────────┘
                                  │ observable (possibly degraded)
                                  │
                    ┌─────────────▼──────────────────────────────────────┐
                    │           CrewAI Sequential Crew                   │
                    │                                                    │
                    │  [1] Triage Agent  ──► TriageReport                │
                    │  [2] Diagnosis Agent ──► DiagnosisReport           │
                    │  [3] Remediation Agent ──► RemediationPlan         │
                    │  [4] Approval Gate ──► ApprovalDecision            │
                    │  [5] Verification + Postmortem Agent               │
                    │       ──► VerificationReport + PostmortemReport    │
                    │                                                    │
                    │  All agents: build_llm() → TrueFoundry Gateway    │
                    │             (Grok primary / Claude / Gemini)       │
                    └─────────────┬──────────────────────────────────────┘
                                  │ RunResult
                                  ▼
                    ┌─────────────────────────────┐
                    │   audit.log_event()         │
                    │   SQLite: events + runs     │  ◄─ every stage written atomically
                    └─────────────────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  evaluation.evaluate_all() │
                    │  scores vs ground_truth    │  ◄─ eval harness only; agents never see this
                    │  writes results to SQLite  │
                    └────────────────────────────┘
```

---

## Repo Map

| File | Purpose | Track |
|---|---|---|
| `config.py` | `build_llm()` — routes every agent through the TrueFoundry gateway | Shared (read-only) |
| `incidents.py` | `load_incidents()`, `get_incident()`, `observable()` — data access | Shared (read-only) |
| `incidents.json` | 5 labeled incidents (alert + telemetry + ground_truth) | Shared (read-only) |
| `.env` / `.env.example` | Gateway URL, API key, model IDs | Shared (read-only) |
| `schemas.py` | All Pydantic artifact types — the integration contract | **Track A authors** |
| `agents.py` | The 5 CrewAI Agent definitions (created Phase 2) | **Track A** |
| `pipeline.py` | `run_incident()` — orchestrates the crew (created Phase 3) | **Track A** |
| `main.py` | Phase 1 CLI runner; becomes the demo CLI entry-point | **Track A** |
| `audit.py` | SQLite event log — `init_db`, `log_event`, `get_run` | **Track B** |
| `chaos.py` | `apply_chaos()` — degrades the observable before agents see it | **Track B** |
| `evaluation.py` | `evaluate_all()` — runs all 5 incidents, scores vs ground_truth | **Track B** |
| `app.py` | Streamlit UI — incident picker, artifacts, chaos console, eval | **Track B** |
| `requirements.txt` | Python dependencies | Both update as needed |

**Rule:** never edit a file the other track owns. If a contract change in `schemas.py` is needed, both teammates agree before A edits it.

---

## Integration Contract

This section is the source of truth. Both tracks build against these exact signatures. Do not change a signature without coordinating first — Track B can be working against a stub of Track A's pipeline and any silent change breaks them.

---

### Schemas (`schemas.py`) — Track A authors

All artifacts are Pydantic `BaseModel` subclasses with strict field types.

```python
class TriageReport(BaseModel):
    severity: str           # "SEV-1" | "SEV-2" | "SEV-3"
    customer_facing: bool
    summary: str            # one-line description
    route_to: str           # which specialist handles next, e.g. "Diagnosis"
    reason: str

class DiagnosisReport(BaseModel):
    root_cause: str
    cited_evidence: list[str]   # telemetry keys / log snippets the agent named
    confidence: float           # 0.0–1.0; computed by the pipeline, not the LLM
    reasoning: str              # the agent's chain-of-thought

class RemediationAction(BaseModel):
    action: str
    rationale: str
    destructive: bool           # True → requires human approval

class RemediationPlan(BaseModel):
    safe: list[RemediationAction]   # non-destructive; execute immediately
    risky: list[RemediationAction]  # destructive; gated behind approval_callback

class ApprovalDecision(BaseModel):
    approved: bool
    approver: str   # "human-ui" | "auto-cli" | "voice" etc.
    note: str

class VerificationReport(BaseModel):
    recovered: bool
    metric_name: str
    observed_value: float
    threshold: float
    note: str

class PostmortemReport(BaseModel):
    summary: str
    timeline: list[str]     # ordered sequence of key events
    root_cause: str
    actions_taken: list[str]
    follow_ups: list[str]

class RunResult(BaseModel):
    run_id: str             # uuid4 string
    incident_id: str
    triage: TriageReport
    diagnosis: DiagnosisReport
    remediation: RemediationPlan
    approval: ApprovalDecision
    verification: VerificationReport
    postmortem: PostmortemReport
    chaos_config: dict | None   # echoes back what chaos was active, None = no chaos
```

---

### Pipeline (`pipeline.py`) — Track A

```python
def run_incident(
    incident_id: str,
    chaos_config: dict | None = None,
    approval_callback: Callable[[RemediationPlan], ApprovalDecision] | None = None,
) -> RunResult:
    ...
```

- `incident_id` — must be a valid key in `incidents.json` (e.g. `"INC-001-checkout-db-pool"`).
- `chaos_config` — if provided, passed to `chaos.apply_chaos()` before any agent sees data. `None` means no degradation.
- `approval_callback` — called with the `RemediationPlan` once the Remediation Agent finishes. Must return an `ApprovalDecision`. If `None`, the pipeline auto-approves (useful for CLI testing). The caller supplies this: the Streamlit UI wires it to a button; the CLI wires it to a `y/n` prompt.
- Returns a fully populated `RunResult`. Every field is always present (no `Optional` fields on `RunResult`).
- Calls `audit.log_event()` at every stage internally.

---

### Chaos (`chaos.py`) — Track B

```python
def apply_chaos(observable: dict, chaos_config: dict | None) -> dict:
    ...
```

**Input:** `observable` is the dict returned by `incidents.observable()` — shape `{"alert": str, "telemetry": {"logs": [...], "metrics": {...}, "deploys": [...]}}`.

**`chaos_config` shape:**
```python
{
    "disable_sources": ["logs", "metrics", "deploys"],  # any subset; removes that key from telemetry
    "break_primary_model": bool   # True → pipeline must use fallback model via build_llm(CLAUDE_MODEL_ID)
}
```

**Contract:**
- If `chaos_config` is `None` or `{}`, return `observable` unchanged.
- For each source named in `disable_sources`, replace that key in `telemetry` with its empty equivalent (`[]` for lists, `{}` for dicts).
- `break_primary_model` does not modify the observable dict; the pipeline checks this flag before calling `build_llm()`.
- Never raises — degraded data is valid data.

---

### Audit (`audit.py`) — Track B

```python
def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    ...

def log_event(run_id: str, stage: str, payload: dict) -> None:
    """Append one event row. stage is one of: triage, diagnosis, remediation,
    approval, verification, postmortem. payload is the artifact dict."""
    ...

def get_run(run_id: str) -> list[dict]:
    """Return all event rows for a run_id, ordered by insertion time."""
    ...
```

- SQLite database path: `rescueops_audit.db` in the repo root.
- `init_db()` is called once at app startup and once at the top of `run_incident()` (idempotent).
- `payload` should be the `.model_dump()` of the relevant artifact.

---

### Evaluation (`evaluation.py`) — Track B

```python
def evaluate_all() -> dict:
    ...
```

- Iterates over all 5 incidents in `incidents.json`.
- Calls `pipeline.run_incident(incident_id)` with no chaos and an auto-approve callback.
- Scores each run against `ground_truth` using the criteria below.
- Writes results to `rescueops_audit.db` (a separate `eval_results` table).
- Returns a summary dict:

```python
{
    "incidents_run": int,
    "by_incident": [
        {
            "incident_id": str,
            "severity_correct": bool,
            "evidence_recall": float,      # fraction of expected_evidence items cited
            "remediation_overlap": float,  # fraction of ground_truth safe+risky actions matched
            "recovered": bool,
        },
        ...
    ],
    "aggregate": {
        "severity_accuracy": float,        # fraction correct across all 5
        "mean_evidence_recall": float,
        "mean_remediation_overlap": float,
        "recovery_rate": float,
    }
}
```

---

## Confidence vs Evaluation

These two concepts are **intentionally separate**. Conflating them would mislead judges about system integrity.

### Runtime Confidence (in `DiagnosisReport.confidence`)

- Computed **by the pipeline** (`pipeline.py`), not by the agent's LLM.
- Computed **from the observable only** — the same data slice the agents see.
- Formula: start at `1.0`, subtract a fixed weight for each telemetry source that is empty or disabled:

| Source disabled | Weight deducted |
|---|---|
| `logs` | −0.30 |
| `metrics` | −0.40 |
| `deploys` | −0.20 |

- Minimum confidence: `0.10` (all three sources disabled).
- When a judge disables a source via the Chaos Console, confidence drops mechanically and immediately. The drop is auditable — no LLM reasoning involved.
- **The agent never outputs a confidence number.** The agent produces `root_cause`, `cited_evidence`, and `reasoning`. The pipeline fills `confidence` before finalizing the `DiagnosisReport`.

### Eval-time Evidence Scoring (in `evaluation.py`)

- **Only the eval harness may read `ground_truth`.**
- Agents, the pipeline, chaos, and the Streamlit UI never receive or display `ground_truth`.
- `evidence_recall` = `len(cited ∩ expected) / len(expected)`, where `expected` is `ground_truth.expected_evidence`.
- `severity_correct` = `triage.severity == ground_truth.severity`.

**State this clearly if a judge asks:** confidence is a real-time signal computed from telemetry availability. Eval accuracy is a post-hoc measurement against labeled ground truth. They measure different things.

---

## Ownership

| Track | Files owned | Files read-only |
|---|---|---|
| **Track A** | `schemas.py`, `agents.py`, `pipeline.py`, `main.py` | `config.py`, `incidents.py`, `incidents.json`, `.env` |
| **Track B** | `audit.py`, `chaos.py`, `evaluation.py`, `app.py` | `config.py`, `incidents.py`, `incidents.json`, `.env`, `schemas.py` |

Track B imports from `schemas.py` but never edits it. If a schema change is needed, Track A makes it and notifies Track B immediately — schema changes are breaking changes for B.

---

## Integration Seam

**Track A commits a stub `run_incident()` on day one**, before any real agents exist. This unblocks Track B to build `audit.py`, `chaos.py`, `evaluation.py`, and `app.py` against the real signature.

Minimal stub (Track A commits this to `pipeline.py` first):

```python
import uuid
from schemas import (
    TriageReport, DiagnosisReport, RemediationAction, RemediationPlan,
    ApprovalDecision, VerificationReport, PostmortemReport, RunResult,
)

_CANNED_REMEDIATION = RemediationPlan(
    safe=[RemediationAction(action="Lower concurrency to 8", rationale="Reverses change", destructive=False)],
    risky=[RemediationAction(action="Roll back deploy", rationale="Fastest fix", destructive=True)],
)

def run_incident(incident_id, chaos_config=None, approval_callback=None):
    plan = _CANNED_REMEDIATION
    decision = (
        approval_callback(plan)
        if approval_callback
        else ApprovalDecision(approved=True, approver="auto-cli", note="stub")
    )
    return RunResult(
        run_id=str(uuid.uuid4()),
        incident_id=incident_id,
        triage=TriageReport(severity="SEV-2", customer_facing=True, summary="stub", route_to="Diagnosis", reason="stub"),
        diagnosis=DiagnosisReport(root_cause="stub", cited_evidence=["stub_metric"], confidence=1.0, reasoning="stub"),
        remediation=plan,
        approval=decision,
        verification=VerificationReport(recovered=True, metric_name="stub_metric", observed_value=0.01, threshold=0.05, note="stub"),
        postmortem=PostmortemReport(summary="stub", timeline=["t=0 alert fired"], root_cause="stub", actions_taken=["stub"], follow_ups=["stub"]),
        chaos_config=chaos_config,
    )
```

Track A replaces the internals phase by phase without ever changing the function signature. Track B's code never needs to change as A's implementation matures.

---

## Build Phases

### Track A

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | `config.py`, `incidents.py`, `schemas.TriageReport`, `main.py` (gateway proven) | **(DONE)** |
| 2 | Complete `schemas.py` (all types above); `agents.py` (5 Agent definitions) | All schemas importable; agents instantiate without error |
| 3 | `pipeline.py` — commit **stub** first (unblocks B), then wire Triage + Diagnosis agents | Stub returns valid `RunResult`; real agents produce non-canned artifacts |
| 4 | Wire Remediation → approval_callback → Verification into pipeline | End-to-end run with human approval in CLI |
| 5 | Wire Postmortem agent; integration test with B's `audit` and `chaos` | Full `RunResult` with real postmortem; chaos lowers confidence correctly |

### Track B

| Phase | Deliverable | Done when |
|---|---|---|
| 1 | `audit.py` — `init_db`, `log_event`, `get_run` | Events written to SQLite and retrievable |
| 2 | `chaos.py` — `apply_chaos` | Disabling "metrics" returns `{}` metrics; stub pipeline still returns `RunResult` |
| 3 | `evaluation.py` — `evaluate_all` | Runs all 5 incidents against stub pipeline; returns scored summary dict |
| 4 | `app.py` — Streamlit UI: incident picker, artifact panels, chaos console, approval button, eval tab | Full demo flow works end-to-end with A's stub |
| 5 | Integration pass with A's real pipeline | Confidence drops live in UI when chaos fires; eval shows real scores |

**Cut-line:** if time runs short, drop the **postmortem** first (Phase 5/Track A + postmortem panel in app.py). Chaos injection and the eval dashboard are the two winning demo moments — protect them above all else.

---

## Setup

### Requirements

- Python 3.12
- TrueFoundry AI Gateway access (URL + API key)

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment

Copy `.env.example` to `.env` and fill in all values:

```
TFY_GATEWAY_BASE_URL=https://<your-gateway>.truefoundry.cloud/api/llm
TFY_API_KEY=<your-api-key>
GROK_MODEL_ID=<grok-model-id-as-configured-in-gateway>
CLAUDE_MODEL_ID=<claude-model-id-as-configured-in-gateway>
GEMINI_MODEL_ID=<gemini-model-id-as-configured-in-gateway>
```

Model IDs must match the aliases configured in the TrueFoundry gateway, not the raw vendor IDs.

### Run order

```bash
# Phase 1 (works now): single-incident triage via gateway
python main.py

# Full pipeline (once pipeline.py exists):
python main.py --incident INC-003-redis-cache-outage

# Streamlit UI (once app.py exists):
streamlit run app.py
```

---

## Demo Script

The four-beat run judges see, in order:

**Beat 1 — Live incident**
- Open the Streamlit UI. Select `INC-001-checkout-db-pool` from the incident picker.
- Click **Run**. The five agent stages animate as each artifact appears: `TriageReport` → `DiagnosisReport` (confidence `1.0`, three evidence items cited) → `RemediationPlan` (safe actions listed, risky flagged).

**Beat 2 — Human approval gate**
- The UI pauses at `RemediationPlan`. The risky action ("Roll back deploy checkout-v42") is highlighted.
- Click **Approve** (or **Deny**). The `ApprovalDecision` artifact appears with `approver: human-ui`.
- Pipeline resumes: `VerificationReport` shows `checkout_error_rate` recovered below threshold. `PostmortemReport` appears.

**Beat 3 — Chaos injection**
- With the previous run still displayed, open the **Chaos Console** panel.
- Disable `metrics`. Click **Re-run same incident**.
- New run completes. `DiagnosisReport.confidence` is now `0.60` (metrics weight deducted). The UI shows the drop explicitly. Point out to judges: this is a computed drop, not an LLM guess.
- Optionally also enable `break_primary_model`. Gateway routes to Claude fallback; Traces in TrueFoundry show the switch.

**Beat 4 — Eval dashboard**
- Click the **Eval** tab. Click **Run evaluation (all 5 incidents)**.
- `evaluate_all()` runs in the background. Table appears: per-incident severity accuracy, evidence recall, remediation overlap, recovery rate.
- Show aggregate scores. Point out which incidents are harder (e.g., INC-003 with no deploy signal).

---

## Hard Constraints

These are non-negotiable for this build:

| Constraint | Rationale |
|---|---|
| No real cloud integrations | All data is synthetic; `incidents.json` only |
| No custom model router | TrueFoundry gateway owns all fallback logic; we just call `build_llm()` |
| SQLite, not ClickHouse or Postgres | One file, zero infra, runs anywhere |
| Sequential CrewAI crew | `Process.sequential` — no parallel agents, no subcrews |
| No auth or user registry | Demo-only; single-user Streamlit session |
| Agents never see `ground_truth` | Enforced by `incidents.observable()` — agents receive only `alert` + `telemetry` |
| Confidence computed, not inferred | The pipeline fills `DiagnosisReport.confidence`; no LLM decides the number |
| `approval_callback` is caller-supplied | The pipeline has no UI dependency; the UI (or CLI) wires the button/prompt in |
