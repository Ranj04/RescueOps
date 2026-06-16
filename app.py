"""RescueOps — Streamlit control plane (Track B).

The demo surface that makes the production-readiness story self-evident:
  - Incident Response tab: live agent timeline + the human-in-the-loop approval gate.
  - Evaluation tab: measured accuracy across all labeled incidents.
  - Chaos console (sidebar): degrade telemetry / break the primary model to show
    the system stays up and confidence drops for an auditable reason.

All artifacts come from `pipeline.run_incident` — this UI does not care whether
they are stubbed or real. Confidence is computed by the pipeline; we only display it.
"""
import streamlit as st

import audit
import evaluation
import incidents
import voice
from pipeline import run_incident
from schemas import ApprovalDecision, RemediationPlan

TELEMETRY_SOURCES = ["logs", "metrics", "deploys"]


def build_chaos_config(disable_sources: list[str], break_primary_model: bool) -> dict | None:
    """Turn UI toggles into a chaos_config, or None when nothing is degraded."""
    if not disable_sources and not break_primary_model:
        return None
    return {"disable_sources": list(disable_sources), "break_primary_model": break_primary_model}


def make_approval_callback(approve_risky: bool):
    """The human-in-the-loop gate, passed into run_incident as approval_callback."""
    def _callback(plan: RemediationPlan) -> ApprovalDecision:
        note = (
            "Operator approved risky actions via UI"
            if approve_risky
            else "Operator held risky actions (safe default)"
        )
        return ApprovalDecision(approved=approve_risky, approver="human-ui", note=note)

    return _callback


# ---------------------------------------------------------------- rendering ---

def _render_triage(t) -> None:
    st.subheader("1 · Triage")
    c1, c2 = st.columns(2)
    c1.metric("Severity", t.severity)
    c2.metric("Customer facing", "Yes" if t.customer_facing else "No")
    st.write(t.summary)
    st.caption(f"Route to: {t.route_to} — {t.reason}")


def _render_diagnosis(d, chaos_config) -> None:
    st.subheader("2 · Diagnosis")
    st.metric("Confidence (computed from available telemetry)", f"{d.confidence:.2f}")
    if chaos_config and chaos_config.get("disable_sources"):
        st.caption(
            "Telemetry degraded this run: "
            + ", ".join(chaos_config["disable_sources"])
            + ". Confidence is computed by the pipeline from the sources that remain."
        )
    st.write(f"**Root cause:** {d.root_cause}")
    with st.expander("Cited evidence", expanded=True):
        for ev in d.cited_evidence:
            st.markdown(f"- `{ev}`")
    with st.expander("Reasoning"):
        st.write(d.reasoning)


def _render_remediation(plan, decision, diagnosis=None) -> None:
    st.subheader("3 · Remediation")
    col_safe, col_risky = st.columns(2)
    with col_safe:
        st.markdown("**Safe (auto-applied)**")
        for a in plan.safe:
            st.markdown(f"- {a.action}  \n  _{a.rationale}_")
    with col_risky:
        st.markdown("**Risky (needs approval)**")
        for a in plan.risky:
            status = "approved" if decision.approved else "held"
            st.markdown(f"- {a.action}  `{status}`  \n  _{a.rationale}_")

    st.subheader("4 · Approval gate")
    if decision.approved:
        st.success(f"Risky actions APPROVED by {decision.approver} — {decision.note}")
    else:
        st.warning(f"Risky actions HELD by {decision.approver} — {decision.note}")

    # Optional voice augmentation — the approval decision above is the source of
    # truth; this only reads the prompt aloud and never blocks the flow.
    if st.session_state.get("voice_enabled") and diagnosis is not None and voice.available():
        if st.button("Speak diagnosis + approval prompt"):
            voice.speak(voice.approval_prompt(diagnosis.root_cause, len(plan.risky)))


def _render_verification(v) -> None:
    st.subheader("5 · Verification")
    c1, c2, c3 = st.columns(3)
    c1.metric("Recovered", "Yes" if v.recovered else "No")
    c2.metric(v.metric_name, f"{v.observed_value}")
    c3.metric("Threshold", f"{v.threshold}")
    st.caption(v.note)


def _render_postmortem(p) -> None:
    st.subheader("6 · Postmortem")
    st.write(p.summary)
    with st.expander("Timeline"):
        for item in p.timeline:
            st.markdown(f"- {item}")
    with st.expander("Actions taken / follow-ups"):
        st.markdown("**Actions taken**")
        for a in p.actions_taken:
            st.markdown(f"- {a}")
        st.markdown("**Follow-ups**")
        for f in p.follow_ups:
            st.markdown(f"- {f}")


def _render_timeline(result, chaos_config) -> None:
    _render_triage(result.triage)
    st.divider()
    _render_diagnosis(result.diagnosis, chaos_config)
    st.divider()
    _render_remediation(result.remediation, result.approval, result.diagnosis)
    st.divider()
    _render_verification(result.verification)
    st.divider()
    _render_postmortem(result.postmortem)


def _render_audit(run_id: str) -> None:
    events = audit.get_run(run_id)
    with st.expander(f"Audit log — {len(events)} events (run {run_id[:8]})"):
        for e in events:
            st.markdown(f"`{e['created_at']}` · **{e['stage']}**")


# -------------------------------------------------------------------- tabs ---

def _incident_response_tab(incident_map: dict) -> None:
    result = st.session_state.get("result")
    if result is None:
        st.info("Pick an incident in the sidebar and click **Run incident**.")
        return

    chaos_config = result.chaos_config
    title = incident_map.get(result.incident_id, result.incident_id)
    st.markdown(f"### {title}")
    if chaos_config:
        bits = []
        if chaos_config.get("disable_sources"):
            bits.append("disabled: " + ", ".join(chaos_config["disable_sources"]))
        if chaos_config.get("break_primary_model"):
            bits.append("primary model broken → gateway fails over (see TrueFoundry Traces)")
        st.warning("Chaos active — " + " · ".join(bits))
    _render_timeline(result, chaos_config)
    _render_audit(result.run_id)


def _evaluation_tab() -> None:
    st.markdown("### Evaluation — measured performance vs labeled ground truth")
    st.caption(
        "Runs all incidents with no chaos and an auto-approve callback, scoring each "
        "against ground truth. The live incident run never sees ground truth."
    )
    if st.button("Run evaluation (all 5 incidents)", type="primary"):
        with st.spinner("Scoring all incidents..."):
            st.session_state["eval"] = evaluation.evaluate_all()

    summary = st.session_state.get("eval") or evaluation.get_latest_eval()
    if not summary:
        st.info("No evaluation run yet.")
        return

    agg = summary["aggregate"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Severity accuracy", f"{agg['severity_accuracy']:.0%}")
    c2.metric("Evidence recall", f"{agg['mean_evidence_recall']:.0%}")
    c3.metric("Remediation overlap", f"{agg['mean_remediation_overlap']:.0%}")
    c4.metric("Recovery rate", f"{agg['recovery_rate']:.0%}")
    st.dataframe(summary["by_incident"], use_container_width=True)


# -------------------------------------------------------------------- main ---

def main() -> None:
    st.set_page_config(page_title="RescueOps", page_icon="🚑", layout="wide")
    audit.init_db()

    st.title("RescueOps — production-ready incident first responder")
    st.caption(
        "CrewAI agents + TrueFoundry gateway. Reliability (chaos + model fallback), "
        "governance (human approval + audit log), and measured evaluation."
    )

    incident_list = incidents.load_incidents()
    incident_map = {inc["id"]: inc.get("title", inc["id"]) for inc in incident_list}

    with st.sidebar:
        st.header("Run an incident")
        incident_id = st.selectbox(
            "Incident",
            options=[inc["id"] for inc in incident_list],
            format_func=lambda i: incident_map[i],
        )

        st.subheader("Chaos console")
        disabled = [s for s in TELEMETRY_SOURCES if st.checkbox(f"Disable {s}", key=f"chaos_{s}")]
        break_model = st.checkbox("Break primary model (force gateway fallback)")

        st.subheader("Governance")
        approve_risky = st.radio(
            "Risky actions",
            options=[False, True],
            format_func=lambda v: "Approve (allow risky)" if v else "Deny (hold risky)",
            index=0,
        )
        st.session_state["voice_enabled"] = st.checkbox(
            "Enable voice narration (optional)",
            value=False,
            help="Reads the approval prompt aloud. The approval button is always the primary control.",
        )

        if st.button("Run incident", type="primary"):
            chaos_config = build_chaos_config(disabled, break_model)
            callback = make_approval_callback(approve_risky)
            st.session_state["result"] = run_incident(incident_id, chaos_config, callback)

        st.divider()
        st.caption(
            "Path to production: swap synthetic incidents for live telemetry sources, "
            "enable TrueFoundry guardrails (PII/secret scrubbing) at the gateway, and "
            "deploy the crew behind the same approval + audit controls."
        )

    tab_run, tab_eval = st.tabs(["Incident response", "Evaluation"])
    with tab_run:
        _incident_response_tab(incident_map)
    with tab_eval:
        _evaluation_tab()


if __name__ == "__main__":
    main()
