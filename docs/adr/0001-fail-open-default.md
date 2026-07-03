# ADR 0001: Fail-Open Default

## Status
Accepted

## Context
Custos sits in front of production agent/model traffic. If Custos itself is unavailable or errors, callers still need to make progress.

## Decision
The SDK and gateway default to fail-open: when Custos cannot reach a verdict (timeout, internal error, dependency down), the caller proceeds as if ALLOW was returned, with the failure logged and surfaced in telemetry.

## Consequences
- Availability of the calling system is prioritized over strict enforcement during Custos outages.
- Tenants that need fail-closed behavior for compliance reasons can override this per-tenant in config.

