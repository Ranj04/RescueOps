"""Load the labeled incident scenarios.

Key rule: agents may see `alert` + `telemetry`. They must NEVER see `ground_truth` —
that block exists only for the eval harness (Phase 5) to score a run.
"""
import json
from pathlib import Path

_INCIDENTS_PATH = Path(__file__).parent / "incidents.json"


def load_incidents() -> list[dict]:
    data = json.loads(_INCIDENTS_PATH.read_text())
    return data["incidents"]


def get_incident(incident_id: str) -> dict:
    for inc in load_incidents():
        if inc["id"] == incident_id:
            return inc
    raise KeyError(f"No incident with id {incident_id!r}")


def observable(incident: dict) -> dict:
    """The slice an agent is allowed to see: alert + telemetry, no ground truth."""
    return {"alert": incident["alert"], "telemetry": incident["telemetry"]}
