# ADR 0005: Unknown model_id Routes to REVIEW

## Status
Accepted

## Context
An evaluation request may reference a `model_id` that Custos has never seen registered.

## Decision
Unknown `model_id` results in a REVIEW decision, not ALLOW (too permissive) and not BLOCK (too disruptive for a likely registration gap).

## Consequences
- Forces human/operator visibility the first time a new model shows up unregistered, without hard-blocking production traffic.

