"""RescueOps — Streamlit control plane (Track B).

Bold Typography design system: dark, editorial, type-driven.
Every element earns its place. Confidence is measured, not vibed.
"""
import streamlit as st

import audit
import evaluation
import incidents
import voice
from pipeline import run_incident
from schemas import ApprovalDecision, RemediationPlan

TELEMETRY_SOURCES = ["logs", "metrics", "deploys"]

# ---------------------------------------------------------------------------
# Design system CSS
# ---------------------------------------------------------------------------
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg: #0A0A0A;
    --fg: #FAFAFA;
    --muted: #1A1A1A;
    --muted-fg: #737373;
    --accent: #FF3D00;
    --border: #262626;
    --card: #0F0F0F;
}

/* ── Global resets ── */
.stApp {
    background-color: var(--bg) !important;
    font-family: "Inter Tight", "Inter", system-ui, sans-serif !important;
    letter-spacing: -0.01em;
}

/* Noise texture overlay */
.stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    opacity: 0.015;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
    background-repeat: repeat;
    background-size: 256px 256px;
}

/* ── Kill all border-radius ── */
.stApp [data-testid],
.stApp button,
.stApp input,
.stApp select,
.stApp textarea,
.stApp [class*="Block"],
.stApp [class*="card"],
.stApp details,
.stApp summary,
.stApp [data-testid="stExpander"],
.stApp [data-testid="stMetric"],
.stApp [data-testid="stTab"],
.stApp [data-testid="stDataFrame"],
.stApp [data-testid="stAlert"] {
    border-radius: 0px !important;
}

/* ── Typography hierarchy ── */
h1, .stApp h1 {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 800 !important;
    letter-spacing: -0.04em !important;
    line-height: 1.05 !important;
    font-size: 3rem !important;
    color: var(--fg) !important;
}

h2, .stApp h2 {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.04em !important;
    line-height: 1.1 !important;
    font-size: 1.75rem !important;
    color: var(--fg) !important;
}

h3, .stApp h3 {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
    line-height: 1.2 !important;
    font-size: 1.25rem !important;
    color: var(--fg) !important;
}

p, li, span, .stMarkdown {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    letter-spacing: -0.01em;
}

code, .stCode, [data-testid="stCode"] {
    font-family: "JetBrains Mono", "Fira Code", monospace !important;
    font-size: 0.8rem !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background-color: var(--bg) !important;
    border-right: 1px solid var(--border) !important;
}

section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top: 2rem !important;
}

/* ── Buttons ── */
.stApp button[kind="primary"],
.stApp button[data-testid="stBaseButton-primary"] {
    background-color: var(--accent) !important;
    color: var(--bg) !important;
    border: none !important;
    border-radius: 0px !important;
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    font-size: 0.8rem !important;
    transition: all 150ms cubic-bezier(0.25, 0, 0, 1) !important;
    padding: 0.65rem 1.5rem !important;
}

.stApp button[kind="primary"]:hover,
.stApp button[data-testid="stBaseButton-primary"]:hover {
    background-color: #E63600 !important;
    transform: translateY(-1px);
}

.stApp button[kind="primary"]:active,
.stApp button[data-testid="stBaseButton-primary"]:active {
    transform: translateY(1px) !important;
}

.stApp button[kind="secondary"],
.stApp button[data-testid="stBaseButton-secondary"] {
    background-color: transparent !important;
    color: var(--fg) !important;
    border: 1px solid var(--fg) !important;
    border-radius: 0px !important;
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    font-size: 0.8rem !important;
    transition: all 150ms !important;
}

.stApp button[kind="secondary"]:hover,
.stApp button[data-testid="stBaseButton-secondary"]:hover {
    background-color: var(--fg) !important;
    color: var(--bg) !important;
}

/* ── Inputs & selects ── */
.stApp input, .stApp select, .stApp textarea,
.stApp [data-testid="stSelectbox"] > div,
.stApp [data-baseweb="select"] {
    border-radius: 0px !important;
}

.stApp [data-baseweb="select"] > div {
    background-color: var(--muted) !important;
    border: 1px solid var(--border) !important;
    border-radius: 0px !important;
}

/* ── Tabs ── */
.stApp [data-testid="stTab"] {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    font-size: 0.75rem !important;
    padding: 0.75rem 1.5rem !important;
    border-radius: 0px !important;
    color: var(--muted-fg) !important;
    border-bottom: 2px solid transparent !important;
    transition: all 150ms !important;
}

.stApp [data-testid="stTab"][aria-selected="true"] {
    color: var(--fg) !important;
    border-bottom: 2px solid var(--accent) !important;
    background: transparent !important;
}

.stApp [data-testid="stTab"]:hover {
    color: var(--fg) !important;
}

/* Tab container border */
.stApp [data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background-color: transparent !important;
    border-left: 2px solid var(--accent) !important;
    padding: 0.75rem 1rem !important;
}

[data-testid="stMetric"] label {
    font-family: "JetBrains Mono", monospace !important;
    font-size: 0.65rem !important;
    letter-spacing: 0.15em !important;
    text-transform: uppercase !important;
    color: var(--muted-fg) !important;
}

[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 800 !important;
    font-size: 2rem !important;
    letter-spacing: -0.04em !important;
    color: var(--fg) !important;
}

/* ── Expander ── */
.stApp [data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: 0px !important;
    background-color: transparent !important;
}

.stApp [data-testid="stExpander"] summary {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
    font-size: 0.75rem !important;
    color: var(--muted-fg) !important;
}

.stApp [data-testid="stExpander"] summary:hover {
    color: var(--fg) !important;
}

/* ── Alerts ── */
.stApp [data-testid="stAlert"] {
    border-radius: 0px !important;
    border: none !important;
    border-left: 2px solid !important;
    background-color: var(--muted) !important;
    font-family: "Inter Tight", system-ui, sans-serif !important;
}

/* Success alert */
.stApp [data-testid="stAlert"][data-baseweb-type="positive"],
.stApp .stSuccess [data-testid="stAlert"] {
    border-left-color: #22C55E !important;
}

/* Warning alert */
.stApp [data-testid="stAlert"][data-baseweb-type="warning"],
.stApp .stWarning [data-testid="stAlert"] {
    border-left-color: var(--accent) !important;
}

/* Info alert */
.stApp [data-testid="stAlert"][data-baseweb-type="info"],
.stApp .stInfo [data-testid="stAlert"] {
    border-left-color: var(--muted-fg) !important;
}

/* ── Dividers ── */
.stApp hr {
    border-color: var(--border) !important;
    margin: 2rem 0 !important;
}

/* ── Dataframe ── */
.stApp [data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 0px !important;
}

/* ── Checkboxes & radio ── */
.stApp [data-testid="stCheckbox"] label,
.stApp [data-testid="stRadio"] label {
    font-family: "Inter Tight", system-ui, sans-serif !important;
    font-size: 0.85rem !important;
}

/* ── Spinner ── */
.stApp .stSpinner > div {
    border-top-color: var(--accent) !important;
}

/* ── Custom component: stage label ── */
.stage-label {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted-fg);
    margin-bottom: 0.25rem;
}

.stage-num {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 800;
    font-size: 3.5rem;
    letter-spacing: -0.06em;
    line-height: 1;
    color: var(--border);
    position: absolute;
    top: -0.5rem;
    right: 0;
    z-index: 0;
    user-select: none;
}

.stage-block {
    position: relative;
    padding: 1.5rem 0;
    border-top: 1px solid var(--border);
    overflow: hidden;
}

.stage-title {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 700;
    font-size: 1.1rem;
    letter-spacing: -0.02em;
    color: var(--fg);
    margin-bottom: 0.75rem;
    position: relative;
    z-index: 1;
}

.stage-title .accent-bar {
    display: inline-block;
    width: 1rem;
    height: 2px;
    background: var(--accent);
    margin-right: 0.5rem;
    vertical-align: middle;
}

/* ── Custom metric block ── */
.metric-row {
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
}

.metric-item {
    border-left: 2px solid var(--accent);
    padding: 0.5rem 0 0.5rem 0.75rem;
    min-width: 120px;
}

.metric-label {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.6rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted-fg);
    margin-bottom: 0.15rem;
}

.metric-value {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 800;
    font-size: 1.75rem;
    letter-spacing: -0.04em;
    color: var(--fg);
    line-height: 1.1;
}

.metric-value.accent {
    color: var(--accent);
}

.metric-value.success {
    color: #22C55E;
}

.metric-value.warning {
    color: var(--accent);
}

/* ── Evidence list ── */
.evidence-item {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.78rem;
    color: var(--fg);
    padding: 0.35rem 0;
    border-bottom: 1px solid var(--border);
    letter-spacing: -0.01em;
}

.evidence-item:last-child {
    border-bottom: none;
}

/* ── Remediation actions ── */
.action-card {
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--border);
}

.action-name {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 600;
    font-size: 0.85rem;
    color: var(--fg);
    letter-spacing: -0.01em;
}

.action-rationale {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-size: 0.78rem;
    color: var(--muted-fg);
    margin-top: 0.15rem;
    line-height: 1.4;
}

.action-badge {
    display: inline-block;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.6rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    padding: 0.15rem 0.5rem;
    margin-left: 0.5rem;
}

.badge-approved {
    border: 1px solid #22C55E;
    color: #22C55E;
}

.badge-held {
    border: 1px solid var(--accent);
    color: var(--accent);
}

.badge-safe {
    border: 1px solid var(--muted-fg);
    color: var(--muted-fg);
}

/* ── Chaos banner ── */
.chaos-banner {
    border: 1px solid var(--accent);
    border-left: 3px solid var(--accent);
    background: rgba(255, 61, 0, 0.05);
    padding: 0.75rem 1rem;
    margin-bottom: 1.5rem;
}

.chaos-banner-label {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.6rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 0.25rem;
}

.chaos-banner-detail {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-size: 0.82rem;
    color: var(--fg);
    line-height: 1.5;
}

/* ── Audit log ── */
.audit-entry {
    display: flex;
    gap: 1rem;
    padding: 0.3rem 0;
    border-bottom: 1px solid var(--border);
    align-items: baseline;
}

.audit-time {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.65rem;
    color: var(--muted-fg);
    flex-shrink: 0;
    letter-spacing: 0.02em;
}

.audit-stage {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 600;
    font-size: 0.78rem;
    color: var(--fg);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* ── Hero header ── */
.hero-title {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 900;
    font-size: 3.5rem;
    letter-spacing: -0.05em;
    line-height: 1;
    color: var(--fg);
    margin-bottom: 0.5rem;
}

.hero-title .accent {
    color: var(--accent);
}

.hero-sub {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.7rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--muted-fg);
    line-height: 1.8;
}

/* ── Section headers ── */
.section-header {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 800;
    font-size: 2rem;
    letter-spacing: -0.04em;
    line-height: 1.1;
    color: var(--fg);
    margin-bottom: 0.25rem;
}

.section-sub {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-size: 0.85rem;
    color: var(--muted-fg);
    line-height: 1.5;
    max-width: 600px;
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 4rem 2rem;
    border: 1px dashed var(--border);
}

.empty-state-title {
    font-family: "Inter Tight", system-ui, sans-serif;
    font-weight: 700;
    font-size: 1.1rem;
    letter-spacing: -0.02em;
    color: var(--muted-fg);
    margin-bottom: 0.5rem;
}

.empty-state-hint {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.7rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted-fg);
    opacity: 0.6;
}

/* ── Path to production footer ── */
.prod-path {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.65rem;
    letter-spacing: 0.05em;
    color: var(--muted-fg);
    line-height: 1.7;
    border-top: 1px solid var(--border);
    padding-top: 0.75rem;
    margin-top: 1rem;
}

/* ── Sidebar section titles ── */
.sidebar-section {
    font-family: "JetBrains Mono", monospace;
    font-size: 0.6rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted-fg);
    margin: 1.25rem 0 0.5rem 0;
    padding-bottom: 0.25rem;
    border-bottom: 1px solid var(--border);
}

/* ── Eval table ── */
.eval-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0;
    border: 1px solid var(--border);
    margin: 1.5rem 0;
}

.eval-cell {
    padding: 1rem;
    border-right: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
}

.eval-cell:nth-child(4n) {
    border-right: none;
}

/* ── Timeline connector ── */
.timeline-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    background: var(--accent);
    margin-right: 0.5rem;
    flex-shrink: 0;
    margin-top: 0.4rem;
}

.timeline-entry {
    display: flex;
    align-items: flex-start;
    padding: 0.3rem 0;
    font-family: "Inter Tight", system-ui, sans-serif;
    font-size: 0.82rem;
    color: var(--fg);
    line-height: 1.4;
}

/* Hide default Streamlit header/footer */
header[data-testid="stHeader"] {
    background-color: var(--bg) !important;
}

footer {
    display: none !important;
}
</style>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_chaos_config(disable_sources: list[str], break_primary_model: bool) -> dict | None:
    if not disable_sources and not break_primary_model:
        return None
    return {"disable_sources": list(disable_sources), "break_primary_model": break_primary_model}


def make_approval_callback(approve_risky: bool):
    def _callback(plan: RemediationPlan) -> ApprovalDecision:
        note = (
            "Operator approved risky actions via UI"
            if approve_risky
            else "Operator held risky actions (safe default)"
        )
        return ApprovalDecision(approved=approve_risky, approver="human-ui", note=note)
    return _callback


def _html(content: str) -> None:
    st.markdown(content, unsafe_allow_html=True)


def _stage_header(num: int, title: str) -> None:
    _html(f"""
    <div class="stage-block">
        <div class="stage-num">{num:02d}</div>
        <div class="stage-title"><span class="accent-bar"></span>{title}</div>
    </div>
    """)


def _metric_html(label: str, value: str, style: str = "") -> str:
    cls = f"metric-value {style}" if style else "metric-value"
    return f"""
    <div class="metric-item">
        <div class="metric-label">{label}</div>
        <div class="{cls}">{value}</div>
    </div>
    """


# ---------------------------------------------------------------------------
# Rendering — each pipeline stage
# ---------------------------------------------------------------------------

def _render_triage(t) -> None:
    _stage_header(1, "Triage")
    _html(f"""
    <div class="metric-row">
        {_metric_html("Severity", t.severity, "accent" if t.severity == "SEV-1" else "")}
        {_metric_html("Customer Facing", "YES" if t.customer_facing else "NO",
                       "warning" if t.customer_facing else "")}
        {_metric_html("Route To", t.route_to)}
    </div>
    """)
    st.write(t.summary)
    _html(f'<div class="stage-label">Reason: {t.reason}</div>')


def _render_diagnosis(d, chaos_config) -> None:
    _stage_header(2, "Diagnosis")

    conf_style = "success" if d.confidence >= 0.8 else ("warning" if d.confidence >= 0.5 else "accent")
    _html(f"""
    <div class="metric-row">
        {_metric_html("Confidence", f"{d.confidence:.2f}", conf_style)}
    </div>
    """)

    if chaos_config and chaos_config.get("disable_sources"):
        sources = ", ".join(chaos_config["disable_sources"])
        _html(f"""
        <div class="chaos-banner" style="margin-top: 0.75rem;">
            <div class="chaos-banner-label">Telemetry Degraded</div>
            <div class="chaos-banner-detail">
                Sources disabled: <strong>{sources}</strong>.
                Confidence is computed by the pipeline from remaining sources — not by the LLM.
            </div>
        </div>
        """)

    _html(f"""
    <div style="margin-top: 0.75rem;">
        <div class="stage-label">Root Cause</div>
        <div style="font-size: 0.95rem; color: var(--fg); line-height: 1.5; margin-top: 0.25rem;">{d.root_cause}</div>
    </div>
    """)

    with st.expander("CITED EVIDENCE"):
        evidence_html = "".join(f'<div class="evidence-item">{ev}</div>' for ev in d.cited_evidence)
        _html(evidence_html if evidence_html else '<div class="evidence-item" style="color: var(--muted-fg);">No evidence cited</div>')

    with st.expander("REASONING"):
        st.write(d.reasoning)


def _render_remediation(plan, decision, diagnosis=None) -> None:
    _stage_header(3, "Remediation")

    col_safe, col_risky = st.columns(2)

    with col_safe:
        _html('<div class="stage-label">Safe Actions — Auto-Applied</div>')
        for a in plan.safe:
            _html(f"""
            <div class="action-card">
                <div class="action-name">{a.action}<span class="action-badge badge-safe">safe</span></div>
                <div class="action-rationale">{a.rationale}</div>
            </div>
            """)

    with col_risky:
        _html('<div class="stage-label">Risky Actions — Require Approval</div>')
        for a in plan.risky:
            badge_cls = "badge-approved" if decision.approved else "badge-held"
            badge_txt = "approved" if decision.approved else "held"
            _html(f"""
            <div class="action-card">
                <div class="action-name">{a.action}<span class="action-badge {badge_cls}">{badge_txt}</span></div>
                <div class="action-rationale">{a.rationale}</div>
            </div>
            """)

    # Approval gate
    _stage_header(4, "Approval Gate")
    if decision.approved:
        _html(f"""
        <div style="border-left: 3px solid #22C55E; padding: 0.5rem 0.75rem; background: rgba(34,197,94,0.05);">
            <div class="stage-label" style="color: #22C55E;">Approved</div>
            <div style="font-size: 0.82rem; color: var(--fg);">
                {decision.approver} — {decision.note}
            </div>
        </div>
        """)
    else:
        _html(f"""
        <div style="border-left: 3px solid var(--accent); padding: 0.5rem 0.75rem; background: rgba(255,61,0,0.05);">
            <div class="stage-label" style="color: var(--accent);">Held</div>
            <div style="font-size: 0.82rem; color: var(--fg);">
                {decision.approver} — {decision.note}
            </div>
        </div>
        """)

    if st.session_state.get("voice_enabled") and diagnosis is not None and voice.available():
        if st.button("SPEAK DIAGNOSIS"):
            voice.speak(voice.approval_prompt(diagnosis.root_cause, len(plan.risky)))


def _render_verification(v) -> None:
    _stage_header(5, "Verification")
    recovered_style = "success" if v.recovered else "accent"
    _html(f"""
    <div class="metric-row">
        {_metric_html("Recovered", "YES" if v.recovered else "NO", recovered_style)}
        {_metric_html(v.metric_name, f"{v.observed_value}")}
        {_metric_html("Threshold", f"{v.threshold}")}
    </div>
    """)
    _html(f'<div class="stage-label" style="margin-top: 0.5rem;">{v.note}</div>')


def _render_postmortem(p) -> None:
    _stage_header(6, "Postmortem")
    st.write(p.summary)

    with st.expander("TIMELINE"):
        timeline_html = "".join(
            f'<div class="timeline-entry"><div class="timeline-dot"></div>{item}</div>'
            for item in p.timeline
        )
        _html(timeline_html)

    with st.expander("ACTIONS & FOLLOW-UPS"):
        _html('<div class="stage-label">Actions Taken</div>')
        for a in p.actions_taken:
            _html(f'<div class="timeline-entry"><div class="timeline-dot"></div>{a}</div>')
        _html('<div class="stage-label" style="margin-top: 0.75rem;">Follow-Ups</div>')
        for f in p.follow_ups:
            _html(f'<div class="timeline-entry"><div class="timeline-dot"></div>{f}</div>')


def _render_timeline(result, chaos_config) -> None:
    _render_triage(result.triage)
    _render_diagnosis(result.diagnosis, chaos_config)
    _render_remediation(result.remediation, result.approval, result.diagnosis)
    _render_verification(result.verification)
    _render_postmortem(result.postmortem)


def _render_audit(run_id: str) -> None:
    events = audit.get_run(run_id)
    with st.expander(f"AUDIT LOG — {len(events)} EVENTS"):
        for e in events:
            _html(f"""
            <div class="audit-entry">
                <span class="audit-time">{e['created_at'][:19]}</span>
                <span class="audit-stage">{e['stage']}</span>
            </div>
            """)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

def _incident_response_tab(incident_map: dict) -> None:
    result = st.session_state.get("result")
    if result is None:
        _html("""
        <div class="empty-state">
            <div class="empty-state-title">No incident loaded</div>
            <div class="empty-state-hint">Select an incident in the sidebar and click Run</div>
        </div>
        """)
        return

    chaos_config = result.chaos_config
    title = incident_map.get(result.incident_id, result.incident_id)

    _html(f'<div class="section-header">{title}</div>')
    _html(f'<div class="section-sub" style="margin-bottom: 1.5rem;">Run ID: <code>{result.run_id[:12]}</code></div>')

    if chaos_config:
        bits = []
        if chaos_config.get("disable_sources"):
            bits.append("sources disabled: <strong>" + ", ".join(chaos_config["disable_sources"]) + "</strong>")
        if chaos_config.get("break_primary_model"):
            bits.append("primary model broken — gateway failing over (see TrueFoundry Traces)")
        _html(f"""
        <div class="chaos-banner">
            <div class="chaos-banner-label">Chaos Active</div>
            <div class="chaos-banner-detail">{"  ·  ".join(bits)}</div>
        </div>
        """)

    _render_timeline(result, chaos_config)
    _render_audit(result.run_id)


def _evaluation_tab() -> None:
    _html('<div class="section-header">Evaluation</div>')
    _html("""
    <div class="section-sub" style="margin-bottom: 1.5rem;">
        Measured performance vs labeled ground truth. Runs all incidents with no chaos
        and an auto-approve callback. The live run never sees ground truth.
    </div>
    """)

    if st.button("RUN EVALUATION — ALL 5 INCIDENTS", type="primary"):
        with st.spinner("Scoring all incidents against ground truth..."):
            st.session_state["eval"] = evaluation.evaluate_all()

    summary = st.session_state.get("eval") or evaluation.get_latest_eval()
    if not summary:
        _html("""
        <div class="empty-state" style="margin-top: 1.5rem;">
            <div class="empty-state-title">No evaluation run yet</div>
            <div class="empty-state-hint">Click above to score all 5 incidents</div>
        </div>
        """)
        return

    agg = summary["aggregate"]
    _html(f"""
    <div class="metric-row" style="margin: 1.5rem 0;">
        {_metric_html("Severity Accuracy", f"{agg['severity_accuracy']:.0%}",
                       "success" if agg['severity_accuracy'] >= 0.8 else "warning")}
        {_metric_html("Evidence Recall", f"{agg['mean_evidence_recall']:.0%}",
                       "success" if agg['mean_evidence_recall'] >= 0.7 else "warning")}
        {_metric_html("Remediation Overlap", f"{agg['mean_remediation_overlap']:.0%}",
                       "success" if agg['mean_remediation_overlap'] >= 0.7 else "warning")}
        {_metric_html("Recovery Rate", f"{agg['recovery_rate']:.0%}",
                       "success" if agg['recovery_rate'] >= 0.8 else "warning")}
    </div>
    """)

    st.dataframe(summary["by_incident"], use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="RescueOps", page_icon="🔥", layout="wide")
    _html(_CSS)
    audit.init_db()

    # Hero header
    _html("""
    <div style="padding: 1rem 0 2rem 0;">
        <div class="hero-title">RESCUE<span class="accent">OPS</span></div>
        <div class="hero-sub">
            CrewAI Agents · TrueFoundry Gateway · Human-in-the-Loop Governance
        </div>
    </div>
    """)

    incident_list = incidents.load_incidents()
    incident_map = {inc["id"]: inc.get("title", inc["id"]) for inc in incident_list}

    # ── Sidebar ──
    with st.sidebar:
        _html('<div class="hero-title" style="font-size: 1.5rem; margin-bottom: 1.5rem;">RESCUE<span class="accent">OPS</span></div>')

        _html('<div class="sidebar-section">Incident</div>')
        incident_id = st.selectbox(
            "Select incident",
            options=[inc["id"] for inc in incident_list],
            format_func=lambda i: incident_map[i],
            label_visibility="collapsed",
        )

        _html('<div class="sidebar-section">Chaos Console</div>')
        disabled = [s for s in TELEMETRY_SOURCES if st.checkbox(f"Disable {s}", key=f"chaos_{s}")]
        break_model = st.checkbox("Break primary model")

        _html('<div class="sidebar-section">Governance</div>')
        approve_risky = st.radio(
            "Risky actions",
            options=[False, True],
            format_func=lambda v: "APPROVE — allow risky" if v else "DENY — hold risky",
            index=0,
            label_visibility="collapsed",
        )
        st.session_state["voice_enabled"] = st.checkbox("Voice narration", value=False)

        st.markdown("")  # spacer
        if st.button("RUN INCIDENT", type="primary", use_container_width=True):
            chaos_config = build_chaos_config(disabled, break_model)
            callback = make_approval_callback(approve_risky)
            with st.spinner("Running pipeline..."):
                st.session_state["result"] = run_incident(incident_id, chaos_config, callback)

        _html("""
        <div class="prod-path">
            <strong style="color: var(--accent);">Path to production:</strong><br>
            Swap synthetic incidents for live telemetry ·
            Enable TrueFoundry guardrails (PII/secret scrubbing) ·
            Deploy crew behind approval + audit controls
        </div>
        """)

    # ── Main content tabs ──
    tab_run, tab_eval = st.tabs(["INCIDENT RESPONSE", "EVALUATION"])
    with tab_run:
        _incident_response_tab(incident_map)
    with tab_eval:
        _evaluation_tab()


if __name__ == "__main__":
    main()
