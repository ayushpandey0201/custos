# ADR 0002: Precomputed Drift Severity

## Status
Accepted

## Context
Computing PSI/KS drift statistics at request time would blow the gateway p99 latency budget (≤ 50ms).

## Decision
Drift severity is computed asynchronously by a worker (`engines/drift/worker.py`) on a schedule / batch trigger, persisted per model, and simply read (cache/DB lookup) by the DriftEngine on the hot path.

## Consequences
- Drift signal can lag real-world distribution shift by up to one recompute interval.
- Hot path stays fast and has no dependency on heavy stats libraries at request time.

