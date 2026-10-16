"""Review-2 deck content. Plain data; build_review2.py places it.

Kept separate from content.py so the Review-1 deck stays reproducible exactly
as presented. Every number here comes from a measurement in the repo — the
source is named beside it — so the deck cannot drift from the system.
"""

from __future__ import annotations

from content import CONTRIBUTIONS as _R1_CONTRIBUTIONS
from content import GUIDE, GUIDE_DESIGNATION, LITERATURE_COLUMNS, TEAM  # noqa: F401

REVIEW_DATE = "17 October 2026"


# --- Progress since Review-1 -------------------------------------------------
# The commitments on the Review-1 closing slide, each with what actually
# happened. Status words are deliberately plain: Done / In progress / Not started.

PROGRESS = (
    ["Committed at Review-1", "Status", "Evidence"],
    [
        [
            "Admission control: shed load at the door",
            "Done",
            "Gateway refuses past a bounded in-flight limit with 503; the SDK then applies the tenant's fail-open / fail-closed policy",
        ],
        [
            "Move the audit write off the hot path",
            "Done",
            "Dedicated single writer thread; event loop no longer blocks. p99 at 100 req/s: 49 ms → 9 ms",
        ],
        [
            "Validate against real drift (Lending Club)",
            "Done — negative",
            "Pre-registered study, 589,186 real loans: drift gating caught fewer defaults than random review. Reported as measured",
        ],
        [
            "Model and data versioning + retraining trigger",
            "Not started",
            "Moved to the final-review plan",
        ],
        [
            "Re-measure against Postgres",
            "Not started",
            "Harness supports --database-url; needs the Postgres container",
        ],
        [
            "Not committed — added: real RiskEngine",
            "Done",
            "Amount anomaly (robust z-score) + request velocity; the third signal is live instead of a stub",
        ],
    ],
    [0.30, 0.13, 0.57],
)


# --- Literature survey -------------------------------------------------------
# Every entry checked against its published venue. Rows 6 and 7 are new since
# Review-1. Rauba et al. is the paper behind "self-healing ML" — included as the
# contrast it is: it repairs the model autonomously, Custos gates the decision.

LITERATURE = [
    (
        "Hidden Technical Debt in Machine Learning Systems\nSculley et al., Google",
        "NeurIPS",
        "2015",
        "ML code is a small part of a real ML system; data dependencies and glue dominate",
        "Diagnoses the problem; proposes no runtime mechanism",
        "Names the infrastructure gap but does not close it",
    ),
    (
        "A Survey on Concept Drift Adaptation\nGama, Zliobaite, Bifet et al.",
        "ACM Computing Surveys",
        "2014",
        "Canonical taxonomy of drift detectors and adaptation strategies",
        "Offline / streaming learning; no enforcement step",
        "Detection decoupled from any decision",
    ),
    (
        "Learning under Concept Drift: A Review\nLu, Liu, Dong, Gu, Gama, Zhang",
        "IEEE TKDE",
        "2019",
        "Unifies drift detection, understanding and adaptation",
        "Assumes labels arrive; evaluated in batch",
        "Unlabelled live traffic not addressed",
    ),
    (
        "Failing Loudly: Detecting Dataset Shift\nRabanser, Günnemann, Lipton",
        "NeurIPS",
        "2019",
        "Empirical comparison of shift detectors and two-sample tests",
        "Offline batch study; no latency budget",
        "Detectors never placed on a request path",
    ),
    (
        "Data Validation for Machine Learning\nBreck, Polyzotis et al., Google",
        "MLSys",
        "2019",
        "Schema-driven validation of training and serving data in TFX",
        "Validates schema conformance, not distributional trust",
        "Pipeline-time only; no per-request verdict",
    ),
    (
        "Challenges in Deploying Machine Learning: A Survey of Case Studies\nPaleyes, Urma, Lawrence",
        "ACM Computing Surveys",
        "2022",
        "Maps real deployment failures to each stage of the workflow, incl. monitoring and trust",
        "Catalogues the problems; proposes no mechanism",
        "Monitoring named as a gap in practice, left open",
    ),
    (
        "Self-Healing Machine Learning\nRauba, Seedat, Kacprzyk, van der Schaar",
        "NeurIPS",
        "2024",
        "Monitor → diagnose → adapt → test loop; LLM proposes corrective actions",
        "Repairs the model autonomously after degradation; no per-decision audit",
        "Acts on the model, not on the decision in flight; no human checkpoint",
    ),
    (
        "Certificate Transparency\nLaurie, Langley, Kasper, Google",
        "RFC 6962, IETF",
        "2013",
        "Append-only logs that make modification of history detectable",
        "Built for TLS certificates, not model decisions",
        "Tamper-evidence never applied to ML decision records",
    ),
]


# --- Requirements ------------------------------------------------------------
# Review-1's set plus the three added since (marked "new").

REQUIREMENTS = (
    ["", "Functional", "", "Non-functional"],
    [
        ["FR1", "Register models and capture a reference distribution", "NFR1", "Gateway p99 <= 50 ms; 20 ms per-engine cap"],
        ["FR2", "Compute PSI and KS per feature, offline", "NFR2", "A Custos failure must not fail the caller"],
        ["FR3", "Roll per-feature statistics into one severity", "NFR3", "tenant_id on every table and every query"],
        ["FR4", "Evaluate tenant policy rules against request context", "NFR4", "Keys stored as SHA-256; rule text parsed, never eval'd"],
        ["FR5", "Fuse signals into a weighted trust score", "NFR5", "A new signal must not modify existing code"],
        ["FR6", "Return ALLOW / REVIEW / BLOCK with reasons", "NFR6", "Gateway and worker horizontally scalable"],
        ["FR7", "Honour an engine veto over all other signals", "NFR7", "new — Overload is refused, never queued (bounded in-flight)"],
        ["FR8", "Append every decision to a tamper-evident chain", "", "Python 3.11, FastAPI, SQLAlchemy 2, Celery"],
        ["FR9", "Verify a chain and report the first modified entry", "", "React 18 + TypeScript 5, Vite"],
        ["FR10", "Route unregistered models to REVIEW", "", "PostgreSQL 16 + Redis 7; SQLite on one node"],
        ["FR11", "new — Score per-request risk: unusual amount, request velocity", "", ""],
        ["FR12", "new — Never auto-approve a model in the significant drift band", "", ""],
    ],
    [0.06, 0.45, 0.07, 0.42],
)


# --- Implementation status ---------------------------------------------------

MODULE_STATUS = (
    ["Component", "What was built", "Status"],
    [
        ["Drift engine", "PSI and KS in pure Python, monotone severity roll-up, offline worker, cached hot-path read", "Complete"],
        ["Policy engine", "Tokeniser, recursive-descent parser, AST evaluator, veto — no eval anywhere", "Complete"],
        ["Risk engine", "new — robust amount anomaly (median / MAD) + per-customer velocity, per tenant", "Complete"],
        ["Trust engine", "Concurrent fan-out, per-engine timeouts, weighted fusion, 7-rule decision cascade", "Complete"],
        ["Admission control", "new — bounded in-flight gate, 503 shed, audit write moved to a dedicated thread", "Complete"],
        ["Audit chain", "SHA-256 hash chain, race-safe append, verification and evidence export", "Complete"],
        ["Gateway + control plane", "/v1/evaluate, /health, /metrics and 14 control-plane endpoints", "Complete"],
        ["Python SDK", "@guard decorator, fail-open client — standard library only", "Complete"],
        ["Dashboard", "React + TypeScript operator console: models, drift, decisions, audit", "Complete"],
        ["Replay harness", "Real-data drift replay; date-order bug fixed; calibrated on a planted shift", "Complete"],
        ["Lending Club study", "new — pre-registered field study on 589,186 matured loans; results committed", "Complete"],
        ["Versioning + retraining trigger", "Model / data version tracking and a drift-driven retrain signal", "Final review"],
    ],
    [0.21, 0.66, 0.13],
)


# --- Risk engine -------------------------------------------------------------

RISK_COMPONENTS = (
    ["Component", "What it measures", "How", "When it abstains"],
    [
        [
            "Amount",
            "Is this amount unusual for this tenant and model?",
            "Robust z-score against the last 2,000 amounts — median and MAD, so outliers cannot drag the baseline. No risk at z ≤ 3, full risk at z ≥ 10",
            "Fewer than 50 amounts seen: “normal” is not yet known",
        ],
        [
            "Velocity",
            "Is one customer firing requests in a burst?",
            "Requests by the same customer_id in the last 60 s. No risk at ≤ 3, full risk at ≥ 10",
            "No customer / account / subject id in the request",
        ],
        [
            "Combined",
            "Engine score = 1 − worst component",
            "Worst, not average: one red flag is enough",
            "No component can vote → degraded, excluded from fusion",
        ],
    ],
    [0.12, 0.24, 0.40, 0.24],
)


# --- Defects found by our own tooling ----------------------------------------

DEFECTS = (
    ["Found by", "Defect", "Fix"],
    [
        [
            "Load harness (R1)",
            "Published p99 of 0.5 ms measured a timer that stops before the audit write; real figure was 49 ms",
            "Report client-observed latency; now 9 ms at the same rate",
        ],
        [
            "Load harness (R1)",
            "Audit chain dropped entries under concurrency and still verified as intact",
            "Advisory lock + jittered backoff; 0 lost from 2 to 48 writers",
        ],
        [
            "Load harness (R1)",
            "Overload changed verdicts: ~13% flipped ALLOW → REVIEW",
            "Event loop unblocked + admission control: 0 flips under overload",
        ],
        [
            "Unit test (R2)",
            "Replay harness sorted dates as text — “Aug-2018” became the 2007 baseline",
            "Parse dates; regression test on Lending Club's own date format",
        ],
        [
            "Fusion arithmetic (R2)",
            "Adding a live risk signal let a significantly drifted model reach ALLOW",
            "Explicit drift-floor rule in the decision cascade, pinned by tests",
        ],
        [
            "Pre-registered study (R2)",
            "On real loans, drift gating caught fewer defaults than random; the drift floor would escalate 92% of decisions for no gain",
            "Not yet fixed — gating to be rebuilt around risk-ranked review",
        ],
    ],
    [0.17, 0.48, 0.35],
)


# --- Work plan to the final review --------------------------------------------

WORK_PLAN = (
    ["Item", "Why it matters", "Depends on"],
    [
        ["Rebuild gating around risk-ranked review", "On real loans the model's risk ranking caught 2.1× random; drift gating caught less than random", "—"],
        ["Replicate on a second credit dataset", "One dataset cannot support a general claim", "Dataset access"],
        ["Scale-out: multiple gateway workers", "One process saturates near 300 req/s; past that, requests queue before the gate can see them", "Postgres for shared state"],
        ["Postgres load measurement", "SQLite is the pessimistic floor; production runs Postgres", "Docker"],
        ["Self-healing step 1: broken-feed detection + proposed rollback, in shadow", "A dead input feed needs a different repair from a real population shift", "Model versioning"],
        ["Self-healing step 2: human approval queue; every repair on the audit chain", "No repair is applied without a person and a tamper-evident record", "Step 1"],
        ["Final report and paper draft", "Department submission", "All of the above"],
    ],
    [0.30, 0.48, 0.22],
)


# --- Contributions -----------------------------------------------------------
# Review-1 ownership, test count updated. New Review-2 modules are not assigned
# to anyone here: who built what is for the team to state, not to infer.

def contributions(test_count: int):
    headers, rows, cols = _R1_CONTRIBUTIONS
    updated = [
        [name, usn, text.replace("274-test suite", f"{test_count}-test suite")]
        for name, usn, text in rows
    ]
    return headers, updated, cols
