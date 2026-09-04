# Custos

> Runtime trust layer for AI agents & models: policy, drift, and risk signals fused into
> ALLOW / BLOCK / REVIEW decisions, with full audit trail.

Serving infrastructure tells you a model is **running**. Nothing in a typical stack tells you it is
still **reliable** — at the moment it matters, on the request that is about to move money.

Custos sits between an agent and its consequential action and answers one question:

> *Given everything I currently know about this model and this request, should this proceed?*

---

## See it work (30 seconds, no infrastructure)

```bash
python -m examples.fintech_demo.run_demo
```

Starts the real gateway and control plane on localhost, drives them with the real SDK over real
HTTP, and narrates five acts:

| Act | What happens | Verdict |
|---|---|---|
| 1 | An unregistered model asks to disburse money | **REVIEW** — Custos does not guess |
| 2 | Register + baseline, healthy traffic | **ALLOW** — trust 0.99 |
| 3 | The population shifts (incomes fall, utilisation spikes) | drift severity 0.02 → **0.83** |
| 4 | The *same* application, the *same* code, no config change | **REVIEW** — trust 0.48 |
| 5 | A policy veto on a large disbursement | **BLOCK**, then the audit chain catches tampering |

No Docker, no Postgres, no Redis — the system falls back to SQLite and an in-process cache.

Add `--serve` to keep the servers running afterwards and explore:

```bash
python -m examples.fintech_demo.run_demo --serve
```

Then, with the API key it prints:

```bash
cd dashboard && npm install && npm run dev
```

## Full stack

```bash
docker-compose up --build
```

Postgres, Redis, Celery beat, and the three services. Migrations run first and everything else
waits on them.

## Tests

```bash
pytest
```

268 tests: golden-value detector tests, the monotonicity invariant, every row of the decision
matrix, hash-chain tamper detection, SDK fail-open behaviour, and a full lifecycle end to end.

---

## How it works

```
agent ──▶ gateway ──┬──▶ PolicyEngine ─┐
                    ├──▶ DriftEngine  ─┼──▶ weighted fusion ──▶ decision matrix ──▶ audit chain
                    └──▶ RiskEngine   ─┘
```

- **Drift is precomputed.** PSI and KS run offline in a worker; the hot path is one cached read
  and a subtraction. That is what makes a p99 ≤ 50 ms budget achievable (ADR 0002).
- **Degraded ≠ trusted.** An engine with no answer is *excluded* from fusion, never defaulted to
  1.0. Every exclusion is recorded (ADR 0004).
- **Fail-open by default.** If Custos cannot answer, the caller proceeds — loudly, with
  `failed_open=True` — because a trust layer that takes down production gets removed (ADR 0001).
- **Policy rules are parsed, never `eval`'d.** Rule text is tenant-supplied and reaches the hot
  path; a real tokeniser and recursive-descent parser is the only acceptable answer.
- **The audit log is tamper-evident.** `entry_hash = SHA256(prev_hash ‖ canonical_json(payload))`.
  `GET /audit/verify` recomputes the chain and reports the *first broken entry*.

## Integrating

```python
import custos
custos.configure(base_url="http://localhost:8000", api_key=KEY)

@custos.guard(model_id="credit-risk-v3", action="disburse", features="application")
def disburse(*, application): ...
```

BLOCK raises `custos.Blocked`. REVIEW raises `custos.ReviewRequired` — deliberately, so that
"send this to a human" is a decision the caller has to make explicitly rather than something that
silently reads as an ALLOW.

The SDK depends on nothing outside the standard library. It is imported into someone else's
production service; every dependency it carries is a version conflict it can force on them.

---

## Layout

| Path | What it is |
|---|---|
| `shared/` | contract layer — schemas, ORM, cache, config, telemetry |
| `engines/` | the extensibility seam: policy, drift, risk. **Engines never import each other.** |
| `services/gateway/` | data plane — hot path |
| `services/control/` | control plane — cold path |
| `sdk/python/` | the adoption surface |
| `dashboard/` | React + TypeScript operator console |
| `examples/fintech_demo/` | ★ kept working at all times ★ |
| `docs/architecture.md` | **canonical design doc — source of truth** |
| `docs/adr/` | one file per irreversible decision |

See [`docs/architecture.md`](docs/architecture.md) for the full design and
[`docs/adr/`](docs/adr/) for the reasoning behind the decisions that will be questioned later.
