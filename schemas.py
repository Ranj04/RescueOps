"""Structured artifacts each agent emits into the incident timeline.

This is the contract that stops the crew from looking like one LLM response sliced
five ways: every stage produces a distinct, typed artifact. Phase 1 defines Triage
only; Diagnosis / Remediation / Verification / Postmortem schemas are added in Phase 2+.
"""
from pydantic import BaseModel, Field


class TriageReport(BaseModel):
    severity: str = Field(description="One of: SEV-1 (highest), SEV-2, SEV-3")
    customer_facing: bool = Field(description="True if end users are affected")
    summary: str = Field(description="One-line description of what is happening")
    route_to: str = Field(description="Which specialist handles this next, e.g. 'Diagnosis'")
    reason: str = Field(description="Why this severity and routing")
