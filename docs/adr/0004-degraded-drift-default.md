# ADR 0004: Missing Drift Severity Defaults to Degraded-Trust, Not Block

## Status
Accepted

## Context
If a model has no baseline yet, or the worker has not computed severity, the DriftEngine has no signal to report.

## Decision
Missing/unknown drift severity is treated as "trust degraded" (a reduced-confidence, non-vetoing signal) rather than an automatic BLOCK or a silent ALLOW.

## Consequences
- New models are not blocked out of the gate just for lacking a baseline.
- The degraded state is visible in aggregation and audit records, distinguishing it from a confident "no drift" result.

