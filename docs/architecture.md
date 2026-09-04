# Custos — Architecture & Technical Design Document

> Canonical ADD/TDS. Source of truth for system design; all other docs and code should agree with this.

---

## 1. Overview

Custos is a **runtime trust layer**. It sits between an AI agent (or any caller) and the
consequential action that caller is about to take, and answers one question:

> *Given everything I currently know about this model and this request, should this action proceed?*

The answer is one of three verdicts — **ALLOW**, **REVIEW**, **BLOCK** — plus the reasoning
behind it and a tamper-evident record that the decision was made.

The distinction the system exists to draw is between a model that is **running** and a model that
is **reliable**. Serving infrastructure already tells you the first. Nothing in a typical stack
tells you the second at the moment it matters — the moment money moves.

### Why this is not solved by existing tooling

| Layer | Answers | Does not answer |
|---|---|---|
| Model monitoring (Evidently, WhyLabs) | "has this model drifted?" — offline, on a dashboard | "should *this* request proceed, right now?" |
| Feature stores | "what were the inputs?" | "are those inputs still the ones the model was trained for?" |
| API gateways / OPA | "is this caller authorised?" | anything about model reliability |
| MLOps platforms | "is the model deployed and up?" | "is the deployed model still trustworthy?" |

Drift detection exists. Policy engines exist. What does not exist is a component that **fuses
them into a single blocking decision on the request path**, and can prove afterwards what it
decided and why. That is Custos.

### Grounding

The design follows practitioner interviews with production credit-risk teams
(`docs/conversations/`). Three findings shaped it directly:

1. **PSI/CSI monitoring is quarterly, but damage is daily.** Teams described needing
   "leading indicators" because they cannot wait three months for a report. Custos moves the
   same statistics onto the request path.
2. **Most production failures are pipeline breaks, not model decay.** A feature silently pins to
   a constant when an upstream feed dies. So per-feature attribution is a first-class output, not
   a debugging aid — the operator must be able to tell "the population changed" from "the data broke".
3. **In fintech, a wrong automated decision loses money immediately.** Hence a three-way verdict:
   BLOCK for certainty, REVIEW to route to a human, ALLOW only when trust is established.

---

## 2. Goals & Non-Goals

### Goals

| # | Goal | How it is met |
|---|---|---|
| G1 | A single blocking verdict fusing multiple trust signals | Trust Engine + weighted fusion (§8) |
| G2 | Sub-50 ms p99 on the hot path | Precomputed drift (ADR 0002), concurrent fan-out, cached reads |
| G3 | Never take the caller down with us | Fail-open by default (ADR 0001) |
| G4 | Tamper-evident evidence for every decision | SHA-256 hash chain (§9) |
| G5 | Adding a new signal must be additive | Engine registry seam (§6) |
| G6 | Integration in ≤ 5 lines | Python SDK decorator / context manager |
| G7 | Multi-tenant from day one | `tenant_id` on every row and every query (§11) |

### Non-Goals (explicitly out of scope for MVP)

- **Custos does not train, serve or host models.** It observes and gates them.
- **Custos does not explain model predictions.** Attribution here is over *input distributions*, not SHAP-style prediction attribution.
- **Custos does not replace an authorisation layer.** The policy engine covers business rules about model use, not user authentication.
- **Custos does not auto-remediate.** It does not retrain, roll back or reroute. It decides and records; humans act.

---

## 3. System Components

```
                    ┌──────────────────────────────────────────────┐
   caller's code    │  agent / service                             │
                    │    @custos.guard(model_id=…)                 │
                    └───────────────────┬──────────────────────────┘
                                        │  POST /v1/evaluate   (≤50 ms budget)
┌───────────────────────────────────────▼──────────────────────────────────────┐
│ DATA PLANE — services/gateway            hot, stateless, horizontally scaled  │
│                                                                              │
│   auth ──▶ Trust Engine ──┬──▶ PolicyEngine ─┐                               │
│                           ├──▶ DriftEngine  ─┼─▶ aggregate ─▶ decide ─▶ audit│
│                           └──▶ RiskEngine   ─┘   (§8.4)      (§8.6)   (§9)   │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │ read: severity, rules, config                │ append
                ▼                                              ▼
        ┌───────────────┐                              ┌──────────────┐
        │ cache (Redis  │                              │  Postgres    │
        │ or in-process)│◀──── invalidate ─────┐       │  audit chain │
        └───────▲───────┘                      │       └──────────────┘
                │ write severity               │
┌───────────────┴──────────────┐   ┌───────────┴──────────────────────────────┐
│ WORKER — engines/drift        │   │ CONTROL PLANE — services/control         │
│   recompute_drift()           │   │   /tenants /models /config /audit /drift │
│   build_baseline()            │   │   cold: never on the request path        │
│   PSI · KS · severity roll-up │   └──────────────────┬───────────────────────┘
└───────────────────────────────┘                      │
                                                       ▼
                                              ┌──────────────────┐
                                              │ dashboard (React)│
                                              └──────────────────┘
```

**The load-bearing split is data plane vs. control plane.** The gateway does the minimum
possible work per request: three cached reads, one weighted mean, one comparison, one append.
Everything expensive — computing PSI, verifying a hash chain, validating a rule grammar — lives
on the control plane or in the worker, where latency does not matter.

---

## 4. Data Plane (Gateway)

**Budget: p99 ≤ 50 ms.** Everything below follows from that number.

### Request lifecycle

| Step | Work | Cost |
|---|---|---|
| 1 | Resolve API key → `tenant_id` | cached, SHA-256 compare |
| 2 | Load tenant config | cached, 30 s TTL |
| 3 | Check `model_id` is registered | cached, 10 s TTL; evicted on registration |
| 4 | Fan out to enabled engines **concurrently** | bounded by `ENGINE_TIMEOUT_MS` (20 ms) |
| 5 | Fuse signals → trust score | pure function, no I/O |
| 6 | Apply decision matrix | pure function, no I/O |
| 7 | Append to audit chain | one insert |
| 8 | Return verdict | — |
| 9 | *(background)* persist feature vector | off the response path |

### Latency design decisions

- **Fan-out is concurrent, not sequential.** Total engine time is the slowest engine, not the sum.
  A fourth signal is free as long as it fits the same timeout — which is what makes §6's
  extensibility claim real rather than aspirational.
- **Per-engine timeout, not just a global one.** One slow engine is degraded and excluded; the
  other signals still produce a verdict. A timeout is information, and it is recorded.
- **Engines do blocking I/O off the event loop** (`asyncio.to_thread`). Without this the timeout
  is unenforceable — a blocked event loop cannot run the code that would cancel the task.
- **Feature capture is a background task.** The caller is waiting on a decision, not on telemetry.

### Failure behaviour

Anything unexpected in steps 4–8 is caught at the route boundary and becomes a **fail-open ALLOW**
(ADR 0001), logged, counted in `custos_fail_open_total`, and marked in the response with
`degraded_engines: ["*"]`. Tenants who need the opposite set `fail_open: false` and receive 503.

---

## 5. Control Plane

Cold path. Never touched during a decision.

| Endpoint | Purpose |
|---|---|
| `POST /tenants` | Bootstrap a tenant; returns the API key **once** |
| `POST /models` · `GET /models` | Register / list models |
| `POST /models/{id}/baseline` | Capture the reference distribution |
| `POST /models/{id}/recompute` | Force a drift recompute now |
| `GET /models/{id}/drift` | Severity history + per-feature breakdown |
| `GET /config` · `PUT /config` | Engines, weights, thresholds, fail-open |
| `GET /config/rules` · `PUT /config/rules` · `DELETE /config/rules/{id}` | Policy rules |
| `GET /audit` | Paged, filterable audit chain |
| `GET /audit/verify` | Recompute the whole chain; report the first break |
| `GET /audit/export` | Streamed JSON Lines evidence export |
| `GET /audit/decisions` | Denormalised decision stream for the dashboard |

**Validation happens here, deliberately.** A policy rule is parsed when it is written, so a
malformed rule is a 400 to an operator rather than a silently skipped rule on live traffic.
Threshold coherence (`block ≤ review`) is checked on write for the same reason.

---

## 6. Engines (Policy, Drift, Risk)

Every signal implements one interface:

```python
class SignalEngine(ABC):
    name: str
    async def evaluate(self, ctx: EvaluationContext) -> SignalResult: ...
```

`SignalResult` is always expressed as **trust**, never risk: `score = 1.0` means fully trusted,
`0.0` means certainly not. One dialect, so the Trust Engine can fuse signals without understanding
any of them.

**The one architectural rule: engines never import each other.** All cross-engine flow goes through
the Trust Engine. This is what makes a new signal purely additive — a folder, a `register()` call,
a name in a tenant's config. The moment one engine reads another's output, ordering becomes
load-bearing and that property is gone.

### 6.1 Policy Engine `[MVP-lite]`

Deterministic rules over request facts. Because it answers a question with a definite yes or no,
it is the only engine permitted to raise a **veto**.

Rules use a small grammar, tokenised and parsed into an AST:

```
amount > 500000 and action == "disburse"
region not in ["IN", "SG"]
applicant.age < 21 or utilisation > 0.9
```

**There is no `eval` anywhere in this path, and there never will be.** Rule text is
tenant-supplied and reaches the hot path; `eval` would be a remote code execution hole in the
middle of it. The grammar is small enough to parse properly, so it is parsed properly.

Two safety properties fall out of the design:

- A rule referencing a fact the caller did not send **does not match** — it is never an error and
  never a veto. Adding a rule for an optional field must not start blocking traffic that omits it.
- Incomparable operands (`"high" > 5`) do not match. A bad rule stays inert rather than catastrophic.

### 6.2 Drift Engine `[MVP] ★ the core ★`

Answers "is this model still scoring the population it was trained on?"

On the hot path this engine does **no statistics at all** — one cached read and a subtraction
(`trust = 1 − severity`). All computation is offline (ADR 0002).

**Detectors** (`detectors.py`, pure stdlib Python, no numpy/scipy):

- **PSI** — `Σ (aᵢ − eᵢ) · ln(aᵢ / eᵢ)` over quantile buckets drawn from the reference sample.
  Equal-frequency rather than equal-width bucketing, because credit features are heavily skewed
  and equal-width puts nearly all mass in one bucket.
- **KS** — `max |CDF_expected − CDF_actual|`, computed in a single merge pass. Bucket-free, so it
  catches shifts that fall *inside* a PSI bucket.

Neither returns a p-value. On production volumes every distribution differs significantly; effect
size is what is operationally meaningful.

Both **raise on an empty sample** rather than returning 0.0. Absence of evidence must never be
reported as evidence of stability — the caller turns it into a degraded signal instead.

**Severity roll-up** (`severity.py`):

1. *Per feature*: PSI mapped through the industry bands onto [0,1] — piecewise-linear with knots
   at 0.10 → 0.33 and 0.25 → 0.66, so "severity 0.66" means exactly "PSI just crossed the
   significant threshold". KS can only **raise** a feature's severity, never lower it: the two
   statistics disagreeing means the shift hid inside a bucket, which is grounds for more suspicion.
2. *Across features*: `0.6 · max + 0.4 · mean`.
   - Pure `max` lets one noisy feature dominate the model.
   - Pure `mean` lets fifty stable features bury one dead pipeline — the exact case this is for.
   - Both `max` and `mean` are monotone non-decreasing in every input, so any convex combination
     is too. **The monotonicity invariant therefore holds by construction, not by testing** —
     worse drift can never produce a lower severity, and so can never produce a *higher* trust score.

**Baselines are fixed at registration, never rolling.** Comparing each window to the previous one
makes slow drift invisible: every window looks like the last while the model walks steadily away
from what it was trained on.

### 6.3 Risk Engine `[FUTURE]`

A registered, wired, deliberately unimplemented seam. Returns a **degraded** signal rather than a
confident `1.0`, so an unbuilt engine cannot contribute trust it has not earned. Its exclusion is
visible in every audit record.

---

## 7. Data Model

| Table | Holds | Notes |
|---|---|---|
| `tenants` | tenant, **SHA-256 of API key**, config JSON | plaintext key stored nowhere |
| `models` | registered models + fixed baseline | unknown `model_id` → REVIEW |
| `drift_snapshots` | severity + per-feature PSI/KS | written by worker, read by gateway |
| `feature_samples` | raw live observations | append-only; worker drains it |
| `decisions` | denormalised verdict stream | dashboard reads this, not the chain |
| `audit_entries` | the hash chain | record of truth |
| `policy_rules` | tenant rules | validated on write |

Two tables record every decision on purpose. `audit_entries` is the record of truth but is
expensive to query — reading it honestly means verifying it. `decisions` is a plain indexed table
so the dashboard is a normal `SELECT`.

---

## 8. Decision Logic

### 8.1 Signals

Each enabled engine returns `SignalResult(score ∈ [0,1], degraded, veto, detail)`.

### 8.2 Degraded exclusion

A degraded engine is **excluded from fusion**, not defaulted to 1.0 (ADR 0004). Surviving weights
are renormalised, so removing an engine reweights the rest instead of silently dragging the score
toward zero.

### 8.3 Weights

Default `policy 0.3 · drift 0.5 · risk 0.2`. Drift carries the most weight: it is the signal
nothing else in the stack provides.

### 8.4 Fusion

```
trust = Σ (wᵢ · scoreᵢ) / Σ wᵢ      over non-degraded engines only
```

A weighted mean rather than a product or a min. A product penalises every engine you enable; a min
discards all evidence but one. Both make adding a signal *expensive*, which is precisely backwards.

### 8.5 Veto ceiling

Any veto clamps trust to **0.0**. Not configurable — a veto means "do not proceed", and a tunable
veto is a suggestion.

### 8.6 Decision Matrix

Evaluated as an ordered cascade. **The order is the specification.**

| # | Condition | Decision | Why |
|---|---|---|---|
| 1 | any veto | **BLOCK** | hard stop; nothing overrides it |
| 2 | `trust < block` (0.30) | **BLOCK** | fused evidence is damning |
| 3 | `model_id` not registered | **REVIEW** | ADR 0005 |
| 4 | every engine degraded | **REVIEW** | Custos has no signal at all |
| 5 | `trust < review` (0.60) | **REVIEW** | ambiguous |
| 6 | otherwise | **ALLOW** | trust established |

Row 2 precedes row 3 deliberately: an unregistered model whose signals are *already* damning
should be blocked, not merely flagged.

Every row is a test case in `tests/unit/test_decision_table.py`, and the precedence between rows
is tested separately — precedence is what breaks silently in a refactor.

### 8.7 Reasons

Every verdict carries ordered, human-readable reasons. This is product surface, not debug output:
**a BLOCK the caller cannot explain to their customer is a BLOCK they will switch off.**

---

## 9. Audit & Evidence Chain

```
entry_hash = SHA256( prev_hash ‖ canonical_json(payload) )
```

Per-tenant chains, contiguous sequence numbers, genesis `prev_hash = "0" × 64`. Payloads are
serialised with sorted keys so a given payload always hashes identically.

**The claim is tamper-*evidence*, not tamper-*proofing*.** Anyone with database access can rewrite
rows. What they cannot do is rewrite one row without invalidating every hash after it.
`GET /audit/verify` recomputes the chain and reports the **first broken sequence number**, which
localises tampering rather than merely detecting it.

Three attacks, three outcomes:

| Attack | Result |
|---|---|
| Edit a payload | hash mismatch at that entry |
| Edit a payload *and* recompute its hash | successor's `prev_hash` no longer links — break surfaces one entry later |
| Delete an entry | sequence gap |

Covering up any of them requires rewriting the entire chain from that point forward.

**Raw feature values are deliberately excluded from the payload.** They are the caller's customer
data, and an append-only log is the last place it should be duplicated.

Concurrent appends race for a sequence number; the `(tenant_id, seq)` unique constraint turns that
race into an `IntegrityError`, which is retried.

---

## 10. Failure Modes & Fail-Open Behavior

| Failure | Behaviour | Rationale |
|---|---|---|
| Custos unreachable | SDK returns ALLOW, `failed_open=True` | ADR 0001 |
| Gateway internal error | fail-open ALLOW, logged + counted | ADR 0001 |
| Tenant is `fail_open: false` | 503 | compliance override |
| One engine raises | that engine degraded, others proceed | one bug ≠ no verdict |
| One engine times out | degraded after 20 ms | timeout is information |
| **All** engines degraded | **REVIEW** | no signal ≠ trustworthy |
| No drift baseline | drift degraded | ADR 0004 |
| Unknown `model_id` | REVIEW | ADR 0005 |
| Cache down | fall through to database | availability > latency |
| Audit write fails | verdict still returned, error logged | the caller has already acted |

The through-line: **degradation is always explicit and always recorded.** There is no path where
Custos silently reports confidence it does not have.

---

## 11. Multi-Tenancy

- `tenant_id` is on every table except `tenants`, and in every query.
- Authentication is by API key; only the SHA-256 digest is stored, so a database dump yields no
  working credentials. Negative lookups are cached so bad keys cannot be used to hammer the database.
- Config, policy rules, weights, thresholds and fail-open behaviour are all per tenant.
- **Audit chains are per tenant**, so one tenant's volume never affects another's verification cost.
- Isolation is asserted end-to-end in `tests/e2e/test_full_lifecycle.py::test_tenant_isolation_end_to_end`.

---

## 12. Deployment

**Single node, zero infrastructure** — SQLite plus an in-process cache, drift worker callable
directly:

```bash
python -m examples.fintech_demo.run_demo
```

**Full stack** — Postgres, Redis, Celery, three services:

```bash
docker-compose up --build
```

The fallbacks are a design decision, not a shortcut: the system has to be runnable on a laptop for
anyone to evaluate it, and the abstraction that makes that possible (`shared/cache.py`,
`shared/db/session.py`) is the same one that lets it scale out.

Schema is versioned with Alembic and generated from `shared/db/models.py`. Migrations are never
hand-edited.

### Scaling path

| Component | Scales by |
|---|---|
| Gateway | horizontally; stateless, shares Redis + Postgres |
| Worker | horizontally; per-model tasks are independent and idempotent |
| Control plane | rarely the bottleneck; cold path |
| Postgres | read replicas for audit queries; the hot path only writes |

Redis becomes required beyond one gateway process: config invalidation must reach every process at
once rather than waiting out independent TTLs.

---

## 13. What is built vs. what is not

| Component | Status |
|---|---|
| Contract layer, DB models, migrations | **complete** |
| Drift: PSI, KS, severity, worker, engine | **complete** |
| Policy: grammar, parser, engine | **complete** |
| Trust Engine, fusion, decision matrix | **complete** |
| Audit hash chain + verification + export | **complete** |
| Gateway + control plane APIs | **complete** |
| Python SDK (`@guard`, `gate`, fail-open) | **complete** |
| React dashboard | **complete** |
| Fintech demo, end to end | **complete** |
| Test suite | **268 tests passing** |
| Risk engine | seam only, by design `[FUTURE]` |
| Language-agnostic sidecar proxy | not started `[FUTURE]` |
| Helm / Terraform | scaffolded, not populated `[FUTURE]` |
