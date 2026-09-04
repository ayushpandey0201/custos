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
