# ADR 0003: Monorepo

## Status
Accepted

## Context
Custos has multiple services (gateway, control, worker), shared contracts, an SDK, and a dashboard. These evolve together, especially the shared schema layer.

## Decision
Ship all of it in a single repository with a shared Python workspace (`pyproject.toml`) rather than splitting into per-service repos.

## Consequences
- Shared type changes are atomic across services (schema layer + all consumers in one PR).
- Simpler CI/CD and local dev (`docker-compose up`) for a small team.

## Exit Criteria
Split into multiple repos when: (a) teams need independent deploy cadences per service, or (b) the repo becomes a CI bottleneck. Neither is true at MVP scale.

