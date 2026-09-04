"""Deck content: the tables that document the system module by module.

Split out from ``build_deck.py`` so the *content* of the review — which changes
every submission — is editable without touching the OOXML machinery that places
it. Everything here is plain data.

Each table is ``(headers, rows, column_fractions)``. Fractions are of the
table's total width and must sum to 1.0; ``build_deck`` asserts that.
"""

from __future__ import annotations

# --- Literature survey (fills the template's own table on the survey slide) --

LITERATURE = [
    (
        "A Unified Framework for Dataset Shift Detection",
        "NeurIPS Workshop",
        "2019",
        "Formalises covariate, prior and concept shift; two-sample tests (MMD, KS)",
        "Offline batch analysis only",
        "Shift detection never reaches the decision path",
    ),
    (
        "PSI for Credit Scorecard Monitoring",
        "J. Risk Model Validation",
        "2018",
        "PSI bands (0.10 / 0.25) as the scorecard-stability standard",
        "Model-level scalar; quarterly; no feature attribution",
        "No attribution; too slow to prevent loss",
    ),
    (
        "Evidently AI / WhyLabs: open-source ML monitoring",
        "MLOps Systems Track",
        "2022",
        "Automated drift dashboards, alerting, data-quality profiling",
        "Observational; cannot block an action",
        "Detection without enforcement",
    ),
    (
        "Open Policy Agent: policy-based control",
        "CNCF / USENIX",
        "2021",
        "Declarative policy, decoupled decision point, sub-ms evaluation",
        "Policy only; no model-reliability signal",
        "Policy and model trust never fuse",
    ),
]
LITERATURE_COLUMNS = [0.19, 0.13, 0.07, 0.22, 0.20, 0.19]


# --- System design ----------------------------------------------------------

REQUEST_LIFECYCLE = (
    ["#", "Step", "What happens", "Cost on the hot path"],
    [
        ["1", "Authenticate", "X-API-Key → SHA-256 digest → tenant_id", "cached, 60 s TTL"],
        ["2", "Load tenant config", "engines, weights, thresholds, fail-open", "cached, 30 s TTL"],
        ["3", "Check registration", "unknown model_id → REVIEW (ADR 0005)", "cached, 10 s TTL"],
        ["4", "Fan out to engines", "policy, drift, risk run concurrently", "20 ms per-engine cap"],
        ["5", "Fuse signals", "weighted mean over non-degraded engines", "pure function, no I/O"],
        ["6", "Apply decision matrix", "ordered cascade → ALLOW / REVIEW / BLOCK", "pure function, no I/O"],
        ["7", "Append to audit chain", "SHA-256 link to the previous entry", "one INSERT"],
        ["8", "Return verdict", "decision, score, reasons, signals, trace_id", "—"],
        ["9", "Capture features", "stored for the next drift recompute", "background task"],
    ],
    [0.05, 0.20, 0.47, 0.28],
)

MODULES_CONTRACT = (
    ["Module", "Responsibility", "Key design point"],
    [
        ["shared/schemas/", "Pydantic wire + internal contracts: EvaluationRequest, EvaluationContext, SignalResult, Decision", "Every engine speaks trust ∈ [0,1], never risk — one dialect, so fusion needs no interpretation"],
        ["shared/db/models.py", "SQLAlchemy ORM: 7 tenant-scoped tables; single source of schema truth", "Alembic migrations are generated from it, never hand-written"],
        ["shared/db/registry.py", "Cached 'is this model registered?' lookup", "Shared by both planes so the control plane can invalidate what the gateway caches"],
        ["shared/cache.py", "TTL cache: Redis when configured, in-process dict otherwise", "A cache outage degrades to a miss, never an error on the hot path"],
        ["shared/config/", "Per-tenant engines, weights, thresholds, fail-open", "Incoherent thresholds are rejected on write, not tolerated at decision time"],
        ["shared/telemetry/", "Structured JSON logging with trace_id; counters and latency percentiles", "Prometheus exposition without a Prometheus dependency"],
        ["engines/base/", "The SignalEngine ABC — one interface every signal obeys", "evaluate() must not raise; failures become degraded results, never a lost verdict"],
        ["engines/registry.py", "name → class map; tenants enable engines by name", "Adding a signal is a folder plus one register() call — no service code changes"],
    ],
    [0.20, 0.40, 0.40],
)

MODULES_ENGINES = (
    ["Module", "Responsibility", "Key design point"],
    [
        ["engines/policy/rules.py", "Tokeniser, recursive-descent parser and AST evaluator for the rule grammar", "No eval anywhere: rule text is tenant-supplied and reaches the hot path"],
        ["engines/policy/engine.py", "Matches rules against request facts; raises vetoes", "The only engine allowed to veto, because it answers a definite question"],
        ["engines/drift/detectors.py", "psi() and ks_test() — pure stdlib, no NumPy or SciPy", "Both raise on an empty sample rather than reporting 0.0 drift"],
        ["engines/drift/severity.py", "Per-feature band mapping and the cross-feature roll-up", "0.6·max + 0.4·mean — monotone by construction, so worse drift can never score better"],
        ["engines/drift/worker.py", "Offline baseline capture and drift recompute (Celery-optional)", "All statistics live here, never on the request path (ADR 0002)"],
        ["engines/drift/engine.py", "Hot-path read of precomputed severity → trust = 1 − severity", "One cached read and a subtraction; no statistics at request time"],
        ["engines/risk/", "Registered but deliberately unimplemented seam", "Returns degraded, so it cannot contribute trust it has not earned"],
    ],
    [0.22, 0.38, 0.40],
)

MODULES_SERVICES = (
    ["Module", "Responsibility", "Key design point"],
    [
        ["services/gateway/main.py", "FastAPI app, middleware, /v1/evaluate, /health, /metrics", "Wiring only; the verdict comes entirely from trust_engine"],
        ["services/gateway/auth.py", "API-key → tenant resolution", "Only SHA-256 digests are stored; negative results are cached too"],
        ["services/gateway/trust_engine.py", "Orchestrator: concurrent fan-out, gather, fuse, decide, audit", "The only component that knows more than one engine exists"],
        ["services/gateway/aggregate.py", "Weighted fusion, degraded exclusion, veto ceiling", "Degraded engines are excluded and renormalised, never defaulted to 1.0"],
        ["services/gateway/decision.py", "The decision matrix as one ordered cascade", "The order is the specification; every row is a test case"],
        ["services/gateway/audit.py", "Canonical JSON, hash chain append, chain verification", "Tamper-evident, not tamper-proof — and honest about the difference"],
        ["services/control/", "Tenants, models, baselines, config, rules, drift history, audit", "Cold path: free to do slow, correct things the gateway cannot afford"],
        ["services/worker/", "Celery app; hourly recompute across every baselined model", "Tasks are idempotent, so late acknowledgement is safe"],
        ["sdk/python/custos/", "@guard, gate(), fail-open client, verdict → control flow", "Standard library only — no dependency conflicts for the caller"],
        ["dashboard/", "React + TypeScript operator console", "Polling, not websockets: the control plane is deliberately cold"],
    ],
    [0.24, 0.36, 0.40],
)

DECISION_MATRIX = (
    ["#", "Condition", "Decision", "Why this order"],
    [
        ["1", "Any engine raised a veto", "BLOCK", "A hard stop; no weight of agreement can outvote it"],
        ["2", "trust < 0.30 (block threshold)", "BLOCK", "The fused evidence is already damning"],
        ["3", "model_id is not registered", "REVIEW", "Unknown ≠ safe; escalate rather than guess (ADR 0005)"],
        ["4", "Every engine reported degraded", "REVIEW", "Custos has no signal at all — that is not trust"],
        ["5", "trust < 0.60 (review threshold)", "REVIEW", "Ambiguous; route to a human"],
        ["6", "Otherwise", "ALLOW", "Trust established"],
    ],
    [0.05, 0.30, 0.13, 0.52],
)

DATA_MODEL = (
    ["Table", "Holds", "Note"],
    [
        ["tenants", "tenant_id, name, SHA-256 of API key, config JSON", "The plaintext key is stored nowhere"],
        ["models", "registered models and their fixed baseline distribution", "Unregistered model_id → REVIEW"],
        ["drift_snapshots", "severity + per-feature PSI/KS, computed_at", "Written by the worker, read by the gateway"],
        ["feature_samples", "raw live feature observations", "Append-only; the worker drains it"],
        ["decisions", "denormalised verdict stream", "So the dashboard is a plain indexed SELECT"],
        ["audit_entries", "seq, prev_hash, entry_hash, payload", "The record of truth; verified, not just read"],
        ["policy_rules", "tenant-authored rules and their action", "Validated at write time, never at decision time"],
    ],
    [0.18, 0.47, 0.35],
)

DECISIONS = (
    ["ADR", "Decision", "Consequence accepted"],
    [
        ["0001", "Fail open by default when Custos cannot reach a verdict", "Availability of the caller is prioritised over strict enforcement; overridable per tenant"],
        ["0002", "Drift severity is computed offline and read at request time", "The signal can lag by up to one recompute interval — the price of a 50 ms budget"],
        ["0003", "Monorepo for services, shared contracts, SDK and dashboard", "Shared type changes stay atomic; split when deploy cadences diverge"],
        ["0004", "Missing drift severity means degraded trust, not BLOCK", "New models are not blocked for lacking a baseline, and the gap stays visible"],
        ["0005", "Unknown model_id routes to REVIEW, not ALLOW or BLOCK", "Forces operator visibility the first time a model appears unregistered"],
    ],
    [0.08, 0.42, 0.50],
)


# --- Implementation ---------------------------------------------------------

MODULE_STATUS = (
    ["Component", "Modules", "Status", "Evidence"],
    [
        ["Contract layer", "schemas, ORM, migrations, cache, config, telemetry", "Complete", "Alembic migration applies; 7 tables created"],
        ["Drift engine", "detectors, severity, worker, hot-path engine", "Complete", "43 unit tests incl. hand-computed golden values"],
        ["Policy engine", "grammar, parser, AST evaluator, veto handling", "Complete", "Truth table + injection attempts rejected"],
        ["Trust engine", "fan-out, timeouts, fusion, decision matrix", "Complete", "Every matrix row and its precedence tested"],
        ["Audit chain", "hash chain, verification, streamed export", "Complete", "Tamper localised to the exact entry"],
        ["Gateway", "/v1/evaluate, /health, /metrics, middleware", "Complete", "Integration suite green"],
        ["Control plane", "14 endpoints across 5 route modules", "Complete", "Full lifecycle exercised end to end"],
        ["Python SDK", "@guard, gate(), fail-open client, enforcement", "Complete", "29 tests incl. every transport failure"],
        ["Dashboard", "models, drift, decisions, audit, verification", "Complete", "Builds clean; verified against live demo data"],
        ["Fintech demo", "credit model, guarded agent, 3 drift scenarios", "Complete", "Runs end to end in one command"],
        ["Risk engine", "seam registered and wired; logic deferred", "By design", "Returns degraded; excluded from fusion"],
        ["Sidecar proxy", "language-agnostic interceptor", "Not started", "Planned for Review-2"],
    ],
    [0.17, 0.33, 0.12, 0.38],
)

API_SURFACE = (
    ["Method & path", "Plane", "Purpose"],
    [
        ["POST /v1/evaluate", "Gateway", "The hot path — one call, one verdict"],
        ["GET /health", "Gateway", "Database and engine registry status"],
        ["GET /metrics", "Gateway", "Prometheus exposition; decisions, latencies, degradations"],
        ["POST /tenants", "Control", "Bootstrap a tenant; returns the API key once"],
        ["POST /models", "Control", "Register a model so its traffic stops routing to REVIEW"],
        ["GET /models", "Control", "List registered models and baseline status"],
        ["POST /models/{id}/baseline", "Control", "Capture the reference distribution"],
        ["POST /models/{id}/recompute", "Control", "Force a drift recompute now"],
        ["GET /models/{id}/drift", "Control", "Severity history and per-feature breakdown"],
        ["GET / PUT /config", "Control", "Per-tenant engines, weights, thresholds, fail-open"],
        ["GET / PUT / DELETE /config/rules", "Control", "Policy rules; validated at write time"],
        ["GET /audit", "Control", "Paged, filterable audit chain"],
        ["GET /audit/verify", "Control", "Recompute the chain; report the first broken entry"],
        ["GET /audit/export", "Control", "Streamed JSON Lines evidence export"],
    ],
    [0.32, 0.12, 0.56],
)

# Counts below are real. Regenerate them before each review with:
#   pytest tests/unit/test_detectors.py -q --collect-only | tail -1
# and so on per suite — a slide claiming a number a reviewer can check has to be
# right, and these drift every time a test is added.
TEST_COVERAGE = (
    ["Suite", "What it pins down", "Tests"],
    [
        ["unit/test_detectors", "PSI and KS against hand-computed golden values; empty-sample refusal", "21"],
        ["unit/test_severity", "Monotonicity invariant over 500 randomised perturbations", "22"],
        ["unit/test_aggregate", "Weighted mean, degraded exclusion, veto ceiling", "17"],
        ["unit/test_decision_table", "Every row of the decision matrix and the precedence between rows", "26"],
        ["unit/test_hash_chain", "Payload edits, forged hashes, deletions — each detected and localised", "19"],
        ["unit/test_policy_rules", "Grammar truth table; code-injection attempts rejected at parse time", "61"],
        ["unit/test_sdk", "Fail-open under every transport failure; verdict → control flow", "29"],
        ["integration/", "Gateway ↔ engines ↔ DB; drift worker; full control API lifecycle", "69"],
        ["e2e/", "Register → baseline → drift → verdict change → audit → tamper detection", "4"],
    ],
    [0.24, 0.60, 0.16],
)

CONTRIBUTIONS = (
    ["Team member", "USN", "Modules owned"],
    [
        ["«Student Name 1»", "«USN»", "«modules owned»"],
        ["«Student Name 2»", "«USN»", "«modules owned»"],
        ["«Student Name 3»", "«USN»", "«modules owned»"],
    ],
    [0.28, 0.18, 0.54],
)
