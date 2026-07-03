# Custos — Repository Structure

> **Monorepo.** One repo, all services + shared libraries.
> Tags: `[MVP]` = build now · `[MVP-lite]` = thin version now · `[FUTURE]` = seam exists, logic deferred.

---

```
custos/
│
├── README.md                              # Quickstart: run the whole system in <10 min
├── docker-compose.yml                     # [MVP] one-command single-node deployment
├── pyproject.toml                         # Python workspace; ALL deps pinned (reproducible builds)
│
├── docs/
│   ├── architecture.md                    # ← canonical ADD/TDS (source of truth)
│   ├── adr/                               # Architecture Decision Records — one .md per decision
│   │   ├── 0001-fail-open-default.md      # why fail-open is the default behavior
│   │   ├── 0002-precomputed-drift.md      # why drift severity is computed offline, read at runtime
│   │   ├── 0003-monorepo.md               # why one repo; exit criteria for splitting
│   │   ├── 0004-degraded-drift-default.md # why missing severity = trust+degraded, not block
│   │   └── 0005-unknown-model-review.md   # why unknown model_id → REVIEW, not ALLOW
│   └── diagrams/
│       └── .gitkeep                       # source files for any rendered diagrams
│
│
├── shared/                                # ══ CONTRACT LAYER ══ imported by every service
│   │                                      #    Rule: no service defines its own copy of a
│   │                                      #    shared type. Changes here first + migration.
│   ├── __init__.py
│   ├── schemas/                           # Pydantic models = wire + internal contracts
│   │   ├── __init__.py
│   │   ├── evaluation.py                  # EvaluationRequest · EvaluationContext · EvaluationResponse
│   │   ├── signals.py                     # SignalResult · VetoInfo
│   │   └── decision.py                    # Decision enum · DecisionRecord
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py                      # SQLAlchemy ORM — single source of DB schema truth
│   │   └── session.py                     # engine/session factory · health check
│   ├── config/
│   │   ├── __init__.py
│   │   ├── tenant.py                      # TenantConfig model + Redis-cached loader
│   │   └── defaults.py                    # system-wide defaults (thresholds, timeouts, weights)
│   └── telemetry/
│       ├── __init__.py
│       ├── logging.py                     # structured JSON logs; trace_id on every line
│       └── metrics.py                     # counters + histograms (decisions, latencies, degradations)
│
│
├── engines/                               # ══ EXTENSIBILITY SEAM ══
│   │                                      #    Rule: engines NEVER import each other.
│   │                                      #    All cross-engine flow goes through Trust Engine.
│   │                                      #    Adding a new signal = one new sibling folder here.
│   ├── __init__.py
│   ├── registry.py                        # name → class map; tenants enable engines by name in config
│   ├── base/
│   │   ├── __init__.py
│   │   └── engine.py                      # SignalEngine ABC — the ONE interface every engine obeys
│   │                                      #   async def evaluate(ctx) -> SignalResult
│   │
│   ├── policy/                            # [MVP-lite] "Is this action ALLOWED?"
│   │   ├── __init__.py
│   │   ├── engine.py                      # PolicyEngine(SignalEngine)
│   │   └── rules.py                       # Rule model + condition evaluator (tiny grammar in MVP)
│   │
│   ├── drift/                             # [MVP] ★ THE MOAT ★ "Is the model still RELIABLE?"
│   │   ├── __init__.py
│   │   ├── engine.py                      # DriftEngine(SignalEngine): reads severity → SignalResult
│   │   ├── detectors.py                   # psi() · ks_test() — pure functions, heavily unit-tested
│   │   ├── severity.py                    # per-feature PSI/KS results → one severity ∈ [0,1]
│   │   └── worker.py                      # Celery tasks: recompute_drift() · build_baseline()
│   │
│   └── risk/                              # [FUTURE] "How DANGEROUS is this situation?"
│       ├── __init__.py
│       └── engine.py                      # RiskEngine(SignalEngine): neutral stub until built
│
│
├── services/                              # ══ DEPLOYABLE PROCESSES ══
│   │                                      #    Rule: services contain WIRING, not logic.
│   │                                      #    Business logic lives in engines/ and shared/.
│   │
│   ├── gateway/                           # [MVP] DATA PLANE — hot path, p99 ≤ 50 ms
│   │   ├── __init__.py
│   │   ├── main.py                        # FastAPI app factory · middleware stack · routes
│   │   ├── auth.py                        # API-key middleware → tenant resolution
│   │   ├── trust_engine.py                # orchestrator: fan-out ▸ gather ▸ aggregate
│   │   ├── aggregate.py                   # RuntimeTrustScore: weighted fusion + veto handling
│   │   ├── decision.py                    # DecisionEngine: thresholds + vetoes → ALLOW/BLOCK/REVIEW
│   │   └── audit.py                       # build record · hash chain · enqueue to audit writer
│   │
│   ├── control/                           # [MVP] CONTROL PLANE — cold, never on hot path
│   │   ├── __init__.py
│   │   ├── main.py                        # FastAPI app factory · routes
│   │   ├── routes_models.py               # POST /models · POST /models/{id}/baseline · GET /models
│   │   ├── routes_config.py               # PUT /config — tenant engines, weights, thresholds
│   │   ├── routes_audit.py                # GET /audit · GET /audit/export · GET /audit/verify
│   │   └── routes_drift.py                # GET /models/{id}/drift — history for dashboard
│   │
│   └── worker/
│       ├── __init__.py
│       └── celery_app.py                  # Celery app; registers drift worker tasks + audit writer
│
│
├── sdk/
│   ├── python/                            # [MVP] the adoption surface — ≤5 lines to integrate
│   │   └── custos/
│   │       ├── __init__.py
│   │       ├── client.py                  # thin HTTP client: timeout handling + fail-open logic
│   │       ├── guard.py                   # @guard decorator · `with custos.gate(...)` context mgr
│   │       └── enforce.py                 # maps verdict → execute / raise Blocked / route review
│   └── proxy/                             # [FUTURE] language-agnostic sidecar interceptor
│       └── .gitkeep
│
│
├── dashboard/                             # [MVP-lite] React + TypeScript — thin human window
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── views/
│       │   ├── Models.tsx                 # registered models + status
│       │   ├── DriftMonitor.tsx           # per-model severity + per-feature breakdown
│       │   ├── Decisions.tsx              # recent ALLOW/BLOCK/REVIEW stream
│       │   └── AuditLog.tsx               # searchable audit + evidence export + chain verify
│       ├── api/
│       │   └── client.ts                  # typed HTTP client for the control API
│       └── components/
│           └── .gitkeep                   # shared UI components (grows as needed)
│
│
├── migrations/                            # Alembic — schema versioned, NEVER hand-edited
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── .gitkeep                       # migration files land here
│
│
├── deploy/
│   ├── docker-compose.override.yml        # local overrides (dev ports, volume mounts)
│   └── future/                            # [FUTURE] — scaffolded, not populated
│       ├── helm/
│       │   └── .gitkeep
│       └── terraform/
│           └── .gitkeep
│
│
├── examples/
│   └── fintech_demo/                      # ★ KEEP THIS WORKING AT ALL TIMES ★
│       │                                  # Simultaneously: pilot demo · onboarding tutorial
│       │                                  # · e2e test fixture · "does Custos actually work?" proof
│       ├── README.md                      # how to run the demo end-to-end in <5 min
│       ├── model/
│       │   ├── train.py                   # trains a simple XGBoost credit-risk model on sample data
│       │   └── credit_model.pkl           # pre-trained artifact (committed for fast demo startup)
│       ├── agent/
│       │   └── loan_bot.py                # fake auto-decisioner: scores → calls @guard → approve/deny
│       ├── inject_drift.py                # script to inject synthetic drift into the demo data stream
│       └── docker-compose.demo.yml        # spins up demo + full Custos stack together
│
│
└── tests/
    ├── conftest.py                        # shared fixtures: test DB, mock tenant config, sample data
    ├── unit/                              # fast, no I/O, run on every commit
    │   ├── test_detectors.py              # psi() · ks_test() against known distributions (golden tests)
    │   ├── test_severity.py               # roll-up monotonicity: worse drift → never lower severity
    │   ├── test_aggregate.py              # weighted mean · veto ceiling · degraded exclusion
    │   ├── test_decision_table.py         # every row of the decision matrix (§8.6) as a test case
    │   ├── test_hash_chain.py             # chain integrity · tamper detection · chain verify endpoint
    │   └── test_policy_rules.py           # condition matcher truth table · veto short-circuit
    ├── integration/                       # real DB + Redis, no external network
    │   ├── test_gateway_engines.py        # gateway ↔ engines ↔ db round-trip
    │   ├── test_drift_worker.py           # ingest batch → worker → severity persisted + cached
    │   └── test_control_api.py            # register model → baseline → config → audit query
    └── e2e/
        └── test_full_lifecycle.py         # ingest → drift scores → evaluate → audit write → verify chain
```

---

## Folder rules (enforced by convention, checked in code review)

| Folder | Rule |
|---|---|
| `shared/` | No service defines its own copy of a shared type. Schema changes here first + Alembic migration. |
| `engines/` | An engine **may not import another engine**. Cross-engine flow goes through the Trust Engine only. |
| `services/` | Services contain **wiring only** — no business logic. Logic lives in `engines/` and `shared/`. |
| `sdk/` | Integration must be ≤ 5 lines. SDK owns client-side fail-open. |
| `examples/fintech_demo/` | Must run end-to-end at all times. Breaking it is treated as breaking the main build. |
| `docs/adr/` | Every irreversible or "will be questioned later" decision gets one ADR. No exceptions. |
