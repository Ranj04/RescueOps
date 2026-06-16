"""Phase 1 skeleton: load one incident, run the Triage agent through the gateway, print its artifact.

Run:   python main.py
Pass:  prints a structured TriageReport for INC-001, AND the call appears in
       TrueFoundry > Traces (proving it routed through the gateway).
"""
import json
from crewai import Agent, Task, Crew, Process

from config import build_llm
from incidents import get_incident, observable
from schemas import TriageReport

INCIDENT_ID = "INC-001-checkout-db-pool"


def build_triage_agent() -> Agent:
    return Agent(
        role="Incident Triage Engineer",
        goal="Classify an incoming production alert by severity and route it to the right specialist.",
        backstory="A senior on-call engineer who makes fast, calibrated first calls on incident severity.",
        llm=build_llm(),
        verbose=True,
    )


def main() -> None:
    incident = get_incident(INCIDENT_ID)
    agent = build_triage_agent()

    task = Task(
        description=(
            "A production alert just fired. Classify it.\n\n"
            f"OBSERVABLE INCIDENT DATA:\n{json.dumps(observable(incident), indent=2)}\n\n"
            "Decide: severity (SEV-1 is highest), whether it is customer-facing, a one-line "
            "summary, which specialist to route to next, and your reason."
        ),
        expected_output="A structured triage report.",
        agent=agent,
        output_pydantic=TriageReport,
    )

    result = Crew(
        agents=[agent], tasks=[task], process=Process.sequential, verbose=True
    ).kickoff()

    report = getattr(result, "pydantic", None)
    print("\n--- TRIAGE ARTIFACT ---")
    print(report.model_dump_json(indent=2) if report else result)
    print("\nVerify: this call should now appear in TrueFoundry > Traces.")


if __name__ == "__main__":
    main()
