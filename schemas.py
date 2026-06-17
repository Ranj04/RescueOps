"""Structured artifacts each agent emits into the incident timeline.

Every stage produces a distinct, typed artifact — this file is the complete
integration contract between Track A (agents) and Track B (UI/audit/chaos).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TriageReport(BaseModel):
    severity: str = Field(description="One of: SEV-1 (highest), SEV-2, SEV-3")
    customer_facing: bool = Field(description="True if end users are affected")
    summary: str = Field(description="One-line description of what is happening")
    route_to: str = Field(description="Which specialist handles this next, e.g. 'Diagnosis'")
    reason: str = Field(description="Why this severity and routing")


class DiagnosisReport(BaseModel):
    root_cause: str = Field(description="One-sentence root-cause statement")
    cited_evidence: list[str] = Field(description="Telemetry keys / values that support the diagnosis")
    confidence: float = Field(description="0.0–1.0; computed deterministically from telemetry coverage, not by LLM")
    reasoning: str = Field(description="Narrative connecting evidence to root cause")


class RemediationAction(BaseModel):
    action: str = Field(description="Imperative description of what to do")
    rationale: str = Field(description="Why this action addresses the root cause")
    destructive: bool = Field(description="True if the action is hard to reverse (rollback, restart, etc.)")


class RemediationPlan(BaseModel):
    safe: list[RemediationAction] = Field(description="Non-destructive actions; execute without approval gate")
    risky: list[RemediationAction] = Field(description="Destructive actions; require approval before execution")


class ApprovalDecision(BaseModel):
    approved: bool = Field(description="Whether the risky actions are approved to execute")
    approver: str = Field(description="Who or what approved: 'human-ui' | 'auto-cli' | 'auto-reject'")
    note: str = Field(description="Optional human-readable justification")


class VerificationReport(BaseModel):
    recovered: bool = Field(description="True if the incident signal returned to normal")
    metric_name: str = Field(description="The key metric checked post-remediation")
    observed_value: float = Field(description="Metric value at verification time")
    threshold: float = Field(description="The recovery threshold the metric must beat")
    note: str = Field(description="Any additional context about the recovery check")


class PostmortemReport(BaseModel):
    summary: str = Field(description="Executive one-paragraph summary")
    timeline: list[str] = Field(description="Ordered list of timestamped events")
    root_cause: str = Field(description="Confirmed root cause (may refine DiagnosisReport)")
    actions_taken: list[str] = Field(description="Remediation steps that were executed")
    follow_ups: list[str] = Field(description="Action items to prevent recurrence")


class PartialRunResult(BaseModel):
    """Everything produced up to (but not including) the human approval gate.

    Returned by `pipeline.run_until_approval`. The FastAPI backend holds this in
    memory keyed by `run_id` while it waits for a human decision, then passes it
    to `pipeline.resume_after_approval` to finish the run. No risky action has
    been executed at this point.
    """
    run_id: str = Field(description="UUID for this pipeline run")
    incident_id: str = Field(description="The incident that was processed")
    triage: TriageReport
    diagnosis: DiagnosisReport
    remediation: RemediationPlan
    chaos_config: Optional[Dict[str, Any]] = Field(default=None, description="Chaos parameters injected for this run, if any")


class RunResult(BaseModel):
    run_id: str = Field(description="UUID for this pipeline run")
    incident_id: str = Field(description="The incident that was processed")
    triage: TriageReport
    diagnosis: DiagnosisReport
    remediation: RemediationPlan
    approval: ApprovalDecision
    verification: VerificationReport
    postmortem: PostmortemReport
    chaos_config: Optional[Dict[str, Any]] = Field(default=None, description="Chaos parameters injected for this run, if any")
