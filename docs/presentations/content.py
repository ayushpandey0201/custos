"""Deck content: the tables the review deck carries.

Split out from ``build_deck.py`` so the *content* of a review — which changes
every submission — is editable without touching the OOXML machinery that places
it. Everything here is plain data.

Each table is ``(headers, rows, column_fractions)``. Fractions are of the
table's total width and must sum to 1.0; ``build_deck`` asserts that.
"""

from __future__ import annotations

# --- Team -------------------------------------------------------------------

TEAM = [
    ("AYUSH PANDEY", "1BM23AD074"),
    ("VIVEK BOORA", "1BM23AD073"),
    ("NITIN", "1BM24AD404"),
]
GUIDE = "Dr. Shruthi K R"


# --- Literature survey ------------------------------------------------------
# Restricted to top-tier venues and industrial research: IEEE, NeurIPS, ACM
# Computing Surveys, MLSys and IETF. Verify the exact volume/page numbers
# against the published versions before submitting the report.

LITERATURE = [
    (
        "Hidden Technical Debt in Machine Learning Systems\nSculley et al., Google",
        "NeurIPS",
        "2015",
        "Shows ML systems accrue hidden debt: glue code, configuration and data dependencies dominate the codebase",
        "Diagnoses the problem; proposes no runtime mechanism",
        "Names the infrastructure gap but does not close it",
    ),
    (
        "A Survey on Concept Drift Adaptation\nGama, Zliobaite, Bifet et al.",
        "ACM Computing Surveys",
        "2014",
        "Canonical taxonomy of drift; detectors, adaptive windowing, ensemble adaptation",
        "Framed as offline / streaming learning; no enforcement step",
        "Detection is fully decoupled from any decision",
    ),
    (
        "Learning under Concept Drift: A Review\nLu, Liu, Dong, Gu, Gama, Zhang",
        "IEEE TKDE",
        "2019",
        "Consolidates drift detection, understanding and adaptation into one framework",
        "Assumes labels arrive; evaluated in batch",
        "Unlabelled live traffic is not addressed",
    ),
    (
        "Failing Loudly: Detecting Dataset Shift\nRabanser, Gunnemann, Lipton (CMU)",
        "NeurIPS",
        "2019",
        "Empirical comparison of shift detectors; dimensionality reduction plus two-sample tests",
        "Offline batch study; no latency budget considered",
        "Detectors are never placed on a request path",
    ),
    (
        "Data Validation for Machine Learning\nBreck, Polyzotis et al., Google",
        "MLSys",
        "2019",
        "Schema-driven validation of training and serving data in production TFX pipelines",
        "Validates schema conformance, not distributional trust",
        "Pipeline-time only; no per-request verdict",
    ),
    (
        "Certificate Transparency\nLaurie, Langley, Kasper, Google",
        "RFC 6962, IETF",
        "2013",
        "Append-only Merkle-tree logs making modification of history detectable",
        "Designed for TLS certificates, not model decisions",
        "Tamper-evidence never applied to ML decision records",
    ),
]
LITERATURE_COLUMNS = [0.24, 0.12, 0.06, 0.24, 0.18, 0.16]


# --- Requirements -----------------------------------------------------------

REQUIREMENTS = (
    ["", "Functional", "", "Non-functional"],
    [
        ["FR1", "Register models and capture a reference distribution", "NFR1", "Gateway p99 <= 50 ms; 20 ms per-engine cap"],
        ["FR2", "Compute PSI and KS per feature, offline", "NFR2", "A Custos failure must not fail the caller"],
        ["FR3", "Roll per-feature statistics into one severity", "NFR3", "tenant_id on every table and every query"],
        ["FR4", "Evaluate tenant policy rules against request context", "NFR4", "Keys stored as SHA-256; rule text parsed, never eval'd"],
        ["FR5", "Fuse signals into a weighted trust score", "NFR5", "A new signal must not modify existing code"],
        ["FR6", "Return ALLOW / REVIEW / BLOCK with reasons", "NFR6", "Gateway and worker horizontally scalable"],
        ["FR7", "Honour an engine veto over all other signals", "", "Python 3.11, FastAPI, SQLAlchemy 2, Celery"],
        ["FR8", "Append every decision to a tamper-evident chain", "", "React 18 + TypeScript 5, Vite"],
        ["FR9", "Verify a chain and report the first modified entry", "", "PostgreSQL 16 + Redis 7; SQLite on a single node"],
        ["FR10", "Route unregistered models to REVIEW", "", "Docker Compose; runs on a laptop, no services"],
    ],
    [0.05, 0.42, 0.07, 0.46],
)


# --- Implementation ---------------------------------------------------------

MODULE_STATUS = (
    ["Component", "What was built", "Status"],
    [
        ["Contract layer", "Pydantic schemas, SQLAlchemy ORM over 7 tables, Alembic migration, TTL cache, tenant config, JSON logging, metrics", "Complete"],
        ["Drift engine", "PSI and KS in pure stdlib Python, band mapping, monotone severity roll-up, offline Celery worker, cached hot-path read", "Complete"],
        ["Policy engine", "Tokeniser, recursive-descent parser, AST evaluator, veto handling — no eval anywhere", "Complete"],
        ["Trust engine", "Concurrent fan-out with per-engine timeouts, weighted fusion, degraded exclusion, decision matrix", "Complete"],
        ["Audit chain", "SHA-256 chain with race-safe append, verification endpoint, streamed evidence export", "Complete"],
        ["Gateway + control plane", "/v1/evaluate, /health, /metrics and 14 control-plane endpoints across 5 route modules", "Complete"],
        ["Python SDK", "@guard decorator, gate() context manager, fail-open client — standard library only", "Complete"],
        ["Dashboard", "React + TypeScript operator console: models, drift, decisions, audit, chain verification", "Complete"],
        ["Fintech demo", "Credit model, guarded loan agent, three drift scenarios, narrated one-command runner", "Complete"],
        ["Risk engine", "Seam registered and wired; returns degraded so it cannot contribute unearned trust", "By design"],
        ["Sidecar proxy", "Language-agnostic interceptor for non-Python callers", "Review-2"],
    ],
    [0.19, 0.68, 0.13],
)


# --- Data and validation ----------------------------------------------------
# The long form of this argument is docs/DATASET.md. These tables are the two
# points a reviewer needs on a projector: what each kind of data is for, and
# what the controlled half actually proves.

VALIDATION_TRACKS = (
    ["", "Data used", "Question it answers", "Ground truth", "Status"],
    [
        [
            "Calibration",
            "Controlled distributions with shifts of a chosen size, injected into the demo's own feature population",
            "Is the detector correct?",
            "Known — we chose the shift, so the right answer exists",
            "Done · 43 detector tests",
        ],
        [
            "Field",
            "Public real-world credit data, replayed in time order through the same drift code the gateway runs",
            "Does it fire on drift that actually happened?",
            "Unknown — but nobody chose the drift, which is what makes it fair",
            "Harness built · Lending Club run is Review-2",
        ],
    ],
    [0.11, 0.30, 0.19, 0.23, 0.17],
)

CALIBRATION_EVIDENCE = (
    ["What is checked", "How", "Why it could not be done on real data"],
    [
        [
            "PSI is arithmetically right",
            "Checked against a value computed by hand from the definition; KS against a case where the CDF gap is exactly 0.5 by construction",
            "There is no hand-computable right answer for 2.2 million rows",
        ],
        [
            "0σ reads stable",
            "Two draws from the same distribution report PSI 0.030 — below the 0.10 stable band",
            "No real dataset is known to contain zero drift",
        ],
        [
            "1σ reads significant",
            "A one-standard-deviation mean shift reports PSI 1.019 — 4× the 0.25 threshold a credit-risk team already uses",
            "The true shift in real data is unmeasured, so the reading cannot be graded",
        ],
        [
            "Severity never moves the wrong way",
            "500 randomised perturbations: increasing any feature's drift can never lower the reported severity",
            "Requires controlling the input to know which direction is correct",
        ],
        [
            "It refuses to guess",
            "An empty window raises rather than returning 0.0; below MIN_SAMPLES = 30 it reports insufficient data",
            "Reporting 'no drift' for 'no data' is the exact failure the system exists to prevent",
        ],
    ],
    [0.22, 0.46, 0.32],
)


# --- What load testing exposed ----------------------------------------------
# Written up in full in benchmarks/README.md, with the raw sweep in
# benchmarks/results-sqlite.json.

LOAD_FINDINGS = (
    ["What we believed", "What the harness measured", "What we did"],
    [
        [
            "Gateway p99 is 0.5 ms",
            "0.5 ms was the trust engine's own timer, which stops before the audit write. The caller actually waits 49 ms at the ceiling — 98% of the budget, not 1%",
            "Report the client-observed number; treat the internal metric as a component timing, not the request",
        ],
        [
            "The audit chain records every decision",
            "Under concurrent appends, 2 of 96 entries were dropped — and verification still reported the chain intact, because a hash chain detects a modified entry, never a missing one",
            "Per-tenant advisory lock on Postgres, jittered backoff everywhere. 0 lost from 2 to 48 writers",
        ],
        [
            "Overload makes it slow",
            "Overload makes it answer differently: past the ceiling, engines exceed their 20 ms timeout, drop out of fusion, and ~13% of verdicts flip ALLOW to REVIEW on traffic an idle gateway allows",
            "Documented as an operational property; admission control is the Review-2 fix",
        ],
    ],
    [0.20, 0.48, 0.32],
)


# --- Team contributions -----------------------------------------------------
# Adjust these to match how the work was actually divided before submitting.

CONTRIBUTIONS = (
    ["Team member", "USN", "Modules owned"],
    [
        [
            "AYUSH PANDEY", "1BM23AD074",
            "Architecture and ADRs · drift engine (PSI/KS detectors, severity roll-up, offline worker) · trust engine fusion and decision matrix",
        ],
        [
            "VIVEK BOORA", "1BM23AD073",
            "Gateway and control-plane APIs · policy engine and rule grammar · tamper-evident audit chain and evidence export",
        ],
        [
            "NITIN", "1BM24AD404",
            "Python SDK · React operator dashboard · fintech demonstration · 268-test suite across unit, integration and end-to-end",
        ],
    ],
    [0.20, 0.14, 0.66],
)
