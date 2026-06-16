"""CrewAI agent factory functions for the RescueOps incident-response pipeline.

Each function returns a fully-configured Agent. Agents are cheap to construct;
build them fresh per run so there's no shared state between incidents.
"""
from crewai import Agent

from config import build_llm


def build_triage_agent() -> Agent:
    return Agent(
        role="Incident Triage Engineer",
        goal=(
            "Make fast, calibrated first calls on production incident severity "
            "and route the incident to the right specialist."
        ),
        backstory=(
            "A senior on-call engineer with 10+ years triaging production incidents at scale. "
            "Decisive and calm under pressure. You assess customer impact quickly from partial data. "
            "When in doubt about severity, you go higher — false escalations cost less than slow responses."
        ),
        llm=build_llm(),
        verbose=True,
    )


def build_diagnosis_agent() -> Agent:
    return Agent(
        role="Site Reliability Engineer — Root Cause Analyst",
        goal=(
            "Identify the precise root cause of a production incident "
            "by correlating observable telemetry: logs, metrics, and deployment events."
        ),
        backstory=(
            "A principal SRE who specialises in complex failure analysis. "
            "You cross-reference logs, metrics, and deploy events to build a causal chain. "
            "You cite specific evidence with exact values and never speculate beyond what the data shows. "
            "You know that correlation + timing + multiple telemetry signals pointing the same direction "
            "is strong evidence for causation."
        ),
        llm=build_llm(),
        verbose=True,
    )
