"""Incident response pipeline — the integration seam between Track A agents and Track B.

Public API (Track B builds against this signature):
    run_incident(incident_id, chaos_config=None, approval_callback=None) -> RunResult

Phase A2: triage + diagnosis use real CrewAI agents via the TrueFoundry gateway.
          Remediation / Verification / Postmortem remain stubbed (A3+).
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any, Dict, Optional, Tuple

from crewai import Crew, Process, Task

from agents import build_diagnosis_agent, build_triage_agent
from incidents import get_incident, observable
from schemas import (
    ApprovalDecision,
    DiagnosisReport,
    PostmortemReport,
    RemediationAction,
    RemediationPlan,
    RunResult,
    TriageReport,
    VerificationReport,
)

# ---------------------------------------------------------------------------
# Optional Track-B dependencies — no-op if not yet available
# ---------------------------------------------------------------------------
try:
    from audit import log_event as _log_event  # type: ignore[import-not-found]
    _AUDIT_AVAILABLE = True
except ImportError:
    _AUDIT_AVAILABLE = False

try:
    from chaos import apply_chaos as _apply_chaos  # type: ignore[import-not-found]
    _CHAOS_AVAILABLE = True
except ImportError:
    _CHAOS_AVAILABLE = False


def _log(run_id: str, stage: str, payload: dict) -> None:
    if _AUDIT_AVAILABLE:
        _log_event(run_id, stage, payload)


# ---------------------------------------------------------------------------
# Confidence computed deterministically from telemetry coverage (never by LLM)
# Weights: logs -0.30 | metrics -0.40 | deploys -0.20
# ---------------------------------------------------------------------------
def _compute_confidence(telemetry: dict) -> Tuple[float, str]:
    confidence = 1.0
    missing = []
    if not telemetry.get("logs"):
        confidence -= 0.30
        missing.append("logs (-0.30)")
    if not telemetry.get("metrics"):
        confidence -= 0.40
        missing.append("metrics (-0.40)")
    if not telemetry.get("deploys"):
        confidence -= 0.20
        missing.append("deploys (-0.20)")
    confidence = round(max(0.0, confidence), 2)
    note = ("missing: " + ", ".join(missing)) if missing else "all telemetry sources present"
    return confidence, note


# ---------------------------------------------------------------------------
# Task prompt builders
# ---------------------------------------------------------------------------
def _triage_prompt(obs: dict) -> str:
    return (
        "A production alert has just fired. Classify it by severity and route it "
        "to the right specialist.\n\n"
        f"OBSERVABLE INCIDENT DATA:\n{json.dumps(obs, indent=2)}\n\n"
        "Severity rules:\n"
        "  SEV-1 — customer-facing, major revenue or safety impact, needs immediate escalation\n"
        "  SEV-2 — customer-facing, significant but contained degradation\n"
        "  SEV-3 — non-customer-facing or minor/partial degradation\n\n"
        "Set route_to to \"Diagnosis\" unless this is a confirmed false alarm."
    )


def _diagnosis_prompt(obs: dict, confidence: float, coverage_note: str) -> str:
    return (
        "The Triage Engineer has classified this incident — see context above. "
        "Your job is to diagnose the root cause.\n\n"
        f"OBSERVABLE INCIDENT DATA:\n{json.dumps(obs, indent=2)}\n\n"
        f"CONFIDENCE (pipeline-computed, read-only): {confidence:.2f}\n"
        f"  Basis: {coverage_note}\n"
        f"  You MUST set confidence to exactly {confidence:.2f} — do not change it.\n\n"
        "Output requirements:\n"
        "  root_cause   — one precise sentence naming the specific failure cause\n"
        "  cited_evidence — list the exact telemetry keys and values that support your diagnosis\n"
        f"  confidence   — {confidence:.2f} (this exact value)\n"
        "  reasoning    — narrative connecting the evidence to the root cause"
    )


# ---------------------------------------------------------------------------
# Canned stub artifacts — used for stages not yet implemented (A3+)
# ---------------------------------------------------------------------------
_STUB_PLAN = RemediationPlan(
    safe=[
        RemediationAction(
            action="Lower checkout_worker_concurrency back to 8 via config update",
            rationale="Reverses the concurrency change that caused pool exhaustion without touching the deploy",
            destructive=False,
        ),
        RemediationAction(
            action="Restart checkout pods one-by-one (rolling restart)",
            rationale="Releases stale connections held by workers already in-flight",
            destructive=False,
        ),
    ],
    risky=[
        RemediationAction(
            action="Roll back deploy checkout-v42 to checkout-v41",
            rationale="Fastest path to known-good state; removes the bad concurrency config entirely",
            destructive=True,
        ),
    ],
)

_STUB_VERIFICATION = VerificationReport(
    recovered=True,
    metric_name="checkout_error_rate",
    observed_value=0.01,
    threshold=0.05,
    note="stub — verification agent not yet implemented (A3+)",
)

_STUB_POSTMORTEM = PostmortemReport(
    summary="stub — postmortem agent not yet implemented (A3+)",
    timeline=["14:02 UTC — checkout-v42 deployed", "14:06 UTC — alert fired"],
    root_cause="stub",
    actions_taken=["stub"],
    follow_ups=["stub"],
)


# ---------------------------------------------------------------------------
# Public pipeline entrypoint
# ---------------------------------------------------------------------------
def run_incident(
    incident_id: str,
    chaos_config: Optional[Dict[str, Any]] = None,
    approval_callback: Optional[Callable[[RemediationPlan], ApprovalDecision]] = None,
) -> RunResult:
    """Run the full incident-response pipeline for a given incident.

    Args:
        incident_id:       ID from incidents.json (e.g. "INC-001-checkout-db-pool").
        chaos_config:      Optional chaos parameters injected by Track B before agents see data.
        approval_callback: Called with the RemediationPlan; must return ApprovalDecision.
                           If None, pipeline auto-approves (README contract: useful for CLI testing).
    """
    run_id = str(uuid.uuid4())

    # Load observable slice — agents never see ground_truth
    incident = get_incident(incident_id)
    obs = observable(incident)

    # Apply chaos before agents see data (Track B's chaos.py; passthrough until available)
    if _CHAOS_AVAILABLE and chaos_config:
        try:
            obs = _apply_chaos(obs, chaos_config)
        except Exception:
            pass  # chaos.py not yet compatible; proceed with clean obs

    _log(run_id, "start", {"incident_id": incident_id, "chaos_config": chaos_config})

    # Confidence is computed here, not by the LLM
    confidence, coverage_note = _compute_confidence(obs["telemetry"])

    # --- A2: Real triage + diagnosis agents ---
    triage_agent = build_triage_agent()
    diagnosis_agent = build_diagnosis_agent()

    triage_task = Task(
        description=_triage_prompt(obs),
        expected_output="Structured triage report classifying this incident.",
        agent=triage_agent,
        output_pydantic=TriageReport,
    )

    diagnosis_task = Task(
        description=_diagnosis_prompt(obs, confidence, coverage_note),
        expected_output="Structured diagnosis report identifying the root cause.",
        agent=diagnosis_agent,
        output_pydantic=DiagnosisReport,
        context=[triage_task],
    )

    result = Crew(
        agents=[triage_agent, diagnosis_agent],
        tasks=[triage_task, diagnosis_task],
        process=Process.sequential,
        verbose=True,
    ).kickoff()

    # Extract pydantic outputs; fall back to stubs if the LLM response can't be parsed
    triage: TriageReport = (
        getattr(result.tasks_output[0], "pydantic", None)
        or TriageReport(
            severity="SEV-2",
            customer_facing=True,
            summary="(parse error — see crew logs)",
            route_to="Diagnosis",
            reason="parse error",
        )
    )

    raw_diag: DiagnosisReport = (
        getattr(result.tasks_output[1], "pydantic", None)
        or DiagnosisReport(
            root_cause="(parse error — see crew logs)",
            cited_evidence=[],
            confidence=confidence,
            reasoning="parse error",
        )
    )

    # Always override confidence with the deterministic pipeline value
    diagnosis = raw_diag.model_copy(update={"confidence": confidence})

    _log(run_id, "triage", triage.model_dump())
    _log(run_id, "diagnosis", diagnosis.model_dump())

    # --- A3+ stubs: Remediation / Approval / Verification / Postmortem ---
    plan = _STUB_PLAN
    _log(run_id, "remediation_plan", plan.model_dump())

    if approval_callback is not None:
        decision = approval_callback(plan)
    else:
        decision = ApprovalDecision(
            approved=True,
            approver="auto-cli",
            note="No approval_callback supplied; auto-approved per README contract",
        )
    _log(run_id, "approval", decision.model_dump())

    verification = _STUB_VERIFICATION
    _log(run_id, "verification", verification.model_dump())

    postmortem = _STUB_POSTMORTEM
    _log(run_id, "postmortem", postmortem.model_dump())

    _log(run_id, "complete", {"recovered": verification.recovered})

    return RunResult(
        run_id=run_id,
        incident_id=incident_id,
        triage=triage,
        diagnosis=diagnosis,
        remediation=plan,
        approval=decision,
        verification=verification,
        postmortem=postmortem,
        chaos_config=chaos_config,
    )
