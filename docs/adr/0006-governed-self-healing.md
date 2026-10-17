# ADR 0006: Governed Self-Healing — Custos Proposes, a Person Approves

## Status
Accepted

## Context
Drift detection tells an operator *that* something is wrong. The pre-registered
gating study (`experiments/gating/RESULTS_v1.md`) showed it is a poor
per-decision gate but a reasonable alarm, so the next step is to act on the
alarm. Two failure modes dominate in production, and they need opposite
responses:

- **A broken input feed** — an upstream API dies and a feature pins to a default,
  or stops arriving. The population has not changed; the data has.
- **A population shift** — the inputs arrive normally, but the people behind
  them have changed.

Autonomous self-healing (Rauba et al., NeurIPS 2024) repairs models without a
human and without a record of who decided. That is not acceptable for decisions
that move money.

## Decision
1. **Custos repairs only what it controls: its own gating.** It never retrains,
   rolls back or edits the tenant's model. A retrain is a recorded request to the
   model's owner.
2. **Diagnose before proposing.** Broken feed: an input missing from ≥ 50% of
   recent requests, or stuck on one value in ≥ 90% (each at least 30 points worse
   than in the baseline). Otherwise, significant drift is a population shift.
   A broken feed takes precedence over a concurrent shift.
3. **The playbook.** Broken feed → quarantine the input (decision rule 5: hold
   every decision for review), then release. Population shift → re-baseline
   (undoable) or a retrain request. **Re-baselining is never offered on a broken
   feed**: learning a reference from broken data would make broken data look
   normal.
4. **Shadow test every proposal** by replaying the model's recent recorded
   decisions (up to 500) through the real fusion and decision cascade with the
   repair applied. Re-baselining must also pass a hold-out test: the newer half
   of the window, scored against a reference built from the older half, must not
   be in the significant band — otherwise the population is still moving.
5. **A named person approves.** Nothing changes a verdict until then. A proposal
   whose shadow test failed cannot be approved.
6. **Verify on traffic after the repair**, never on the traffic used to build
   it, and propose the next step (release, rollback, resolve).
7. **Every transition is appended to the tenant's hash chain.**

## Consequences
- The drift window now starts no earlier than the current baseline, and no
  earlier than the verified-healthy traffic after a repaired feed. Before this,
  the baseline's own rows were scored as live traffic, which diluted every
  reading; healthy drift in the demo moved from 0.02 to an honest 0.18.
- After a re-baseline the previous drift reading stays in force until fresh
  traffic is measured against the new reference, so the error is toward REVIEW.
- One quarantine lookup is added to the hot path. It runs concurrently with the
  engines and is served from the in-process cache without a thread hop;
  re-measured p99 at 200 req/s: 31 ms (28 ms before), budget 50 ms.
- Approvers are named, not authenticated: Custos has tenant keys, not user
  accounts. The chain makes a name impossible to change afterwards, not
  impossible to misstate at the time.
- Only two fault signatures are detected. A feed that is wrong but still varies
  (a unit change, a shifted offset) reads as a population shift; the reviewer
  sees the per-input evidence and decides.
