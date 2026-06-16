"""Incident response pipeline — CrewAI Flow orchestrating the sequential crew.

Public API (Track B builds against this signature):
    run_incident(incident_id, chaos_config=None, approval_callback=None) -> RunResult

Uses CrewAI Flows for event-driven orchestration with state management.
Each pipeline stage is a Flow step connected via @start() / @listen().
The Crew (triage + diagnosis agents) runs inside the diagnose step.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any, Dict, List, Optional, Tuple

from crewai import Crew, Process, Task
from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel, Field

from agents import build_diagnosis_agent, build_triage_agent
from config import CLAUDE_MODEL_ID
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
    from audit import log_event as _log_event
    _AUDIT_AVAILABLE = True
except ImportError:
    _AUDIT_AVAILABLE = False

try:
    from chaos import apply_chaos as _apply_chaos
    _CHAOS_AVAILABLE = True
except ImportError:
    _CHAOS_AVAILABLE = False


def _log(run_id: str, stage: str, payload: dict) -> None:
    if _AUDIT_AVAILABLE:
        _log_event(run_id, stage, payload)


# ---------------------------------------------------------------------------
# Confidence computed deterministically from telemetry coverage (never by LLM)
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
# Flow state — persists data across all pipeline steps
# ---------------------------------------------------------------------------
class IncidentFlowState(BaseModel):
    run_id: str = ""
    incident_id: str = ""
    chaos_config: Optional[Dict[str, Any]] = None
    obs: dict = Field(default_factory=dict)
    confidence: float = 1.0
    coverage_note: str = ""
    triage: Optional[Dict[str, Any]] = None
    diagnosis: Optional[Dict[str, Any]] = None
    remediation: Optional[Dict[str, Any]] = None
    approval: Optional[Dict[str, Any]] = None
    verification: Optional[Dict[str, Any]] = None
    postmortem: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# CrewAI Flow — event-driven pipeline orchestration
# ---------------------------------------------------------------------------
class IncidentResponseFlow(Flow[IncidentFlowState]):
    """Flow-based incident response pipeline.

    Each step is an event-driven node connected via @start/@listen.
    The Crew (triage + diagnosis agents) runs inside the diagnose step.
    State is managed by Pydantic across all steps.
    """

    def __init__(self, approval_callback=None, **kwargs):
        super().__init__(**kwargs)
        self._approval_callback = approval_callback

    # Step 1: Load incident data and apply chaos
    @start()
    def load_and_prepare(self):
        incident = get_incident(self.state.incident_id)
        obs = observable(incident)

        if _CHAOS_AVAILABLE and self.state.chaos_config:
            try:
                obs = _apply_chaos(obs, self.state.chaos_config)
            except Exception:
                pass

        self.state.obs = obs
        confidence, coverage_note = _compute_confidence(obs["telemetry"])
        self.state.confidence = confidence
        self.state.coverage_note = coverage_note

        _log(self.state.run_id, "start", {
            "incident_id": self.state.incident_id,
            "chaos_config": self.state.chaos_config,
        })
        return "prepared"

    # Step 2: Run triage + diagnosis crew
    @listen(load_and_prepare)
    def run_crew(self, _):
        # If chaos broke the primary model, fall back to Claude via the gateway
        fallback = None
        if self.state.chaos_config and self.state.chaos_config.get("break_primary_model"):
            fallback = CLAUDE_MODEL_ID

        triage_agent = build_triage_agent(model_id=fallback)
        diagnosis_agent = build_diagnosis_agent(model_id=fallback)

        triage_task = Task(
            description=_triage_prompt(self.state.obs),
            expected_output="Structured triage report classifying this incident.",
            agent=triage_agent,
            output_pydantic=TriageReport,
        )

        diagnosis_task = Task(
            description=_diagnosis_prompt(
                self.state.obs, self.state.confidence, self.state.coverage_note
            ),
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

        # Extract pydantic outputs with fallbacks
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
                confidence=self.state.confidence,
                reasoning="parse error",
            )
        )

        # Override confidence with deterministic pipeline value
        diagnosis = raw_diag.model_copy(update={"confidence": self.state.confidence})

        self.state.triage = triage.model_dump()
        self.state.diagnosis = diagnosis.model_dump()

        _log(self.state.run_id, "triage", self.state.triage)
        _log(self.state.run_id, "diagnosis", self.state.diagnosis)
        return "crew_done"

    # Step 3: Remediation plan (stubbed for A3+)
    @listen(run_crew)
    def remediate(self, _):
        plan = _STUB_PLAN
        self.state.remediation = plan.model_dump()
        _log(self.state.run_id, "remediation_plan", self.state.remediation)
        return "remediation_done"

    # Step 4: Human-in-the-loop approval gate
    @listen(remediate)
    def approve(self, _):
        plan = RemediationPlan(**self.state.remediation)

        if self._approval_callback is not None:
            decision = self._approval_callback(plan)
        else:
            decision = ApprovalDecision(
                approved=True,
                approver="auto-cli",
                note="No approval_callback supplied; auto-approved per README contract",
            )

        self.state.approval = decision.model_dump()
        _log(self.state.run_id, "approval", self.state.approval)
        return "approval_done"

    # Step 5: Verification (stubbed for A3+)
    @listen(approve)
    def verify(self, _):
        verification = _STUB_VERIFICATION
        self.state.verification = verification.model_dump()
        _log(self.state.run_id, "verification", self.state.verification)
        return "verification_done"

    # Step 6: Postmortem (stubbed for A3+)
    @listen(verify)
    def write_postmortem(self, _):
        postmortem = _STUB_POSTMORTEM
        self.state.postmortem = postmortem.model_dump()
        _log(self.state.run_id, "postmortem", self.state.postmortem)
        _log(self.state.run_id, "complete", {"recovered": _STUB_VERIFICATION.recovered})
        return "complete"


# ---------------------------------------------------------------------------
# Public pipeline entrypoint — same signature, now powered by Flow
# ---------------------------------------------------------------------------
def run_incident(
    incident_id: str,
    chaos_config: Optional[Dict[str, Any]] = None,
    approval_callback: Optional[Callable[[RemediationPlan], ApprovalDecision]] = None,
) -> RunResult:
    """Run the full incident-response pipeline for a given incident.

    Internally uses a CrewAI Flow for event-driven orchestration.
    The public signature is unchanged — Track B code works without modification.
    """
    run_id = str(uuid.uuid4())

    flow = IncidentResponseFlow(approval_callback=approval_callback)
    flow.state.run_id = run_id
    flow.state.incident_id = incident_id
    flow.state.chaos_config = chaos_config

    flow.kickoff()

    # Reconstruct RunResult from flow state
    return RunResult(
        run_id=run_id,
        incident_id=incident_id,
        triage=TriageReport(**flow.state.triage),
        diagnosis=DiagnosisReport(**flow.state.diagnosis),
        remediation=RemediationPlan(**flow.state.remediation),
        approval=ApprovalDecision(**flow.state.approval),
        verification=VerificationReport(**flow.state.verification),
        postmortem=PostmortemReport(**flow.state.postmortem),
        chaos_config=chaos_config,
    )
