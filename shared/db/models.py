"""SQLAlchemy ORM models — single source of DB schema truth.

Alembic migrations in migrations/versions/ are generated from this file.

Every table except ``tenants`` carries ``tenant_id`` as the first column of its
primary access path. Multi-tenancy is enforced by always filtering on it — see
docs/architecture.md §11.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """An isolated customer of Custos. Owns models, config, decisions and audit."""

    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    # SHA-256 of the API key. The plaintext key is shown once at creation and
    # never stored, so a database leak does not hand over live credentials.
    api_key_hash: Mapped[str] = mapped_column(String(64), index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Model(Base):
    """A registered model. Unregistered model_ids route to REVIEW (ADR 0005)."""

    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("tenant_id", "model_id", name="uq_models_tenant_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), index=True)
    model_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    version: Mapped[str] = mapped_column(String(64), default="1")
    status: Mapped[str] = mapped_column(String(32), default="active")
    # Reference distribution per feature, captured at registration time. Drift
    # is always measured against this, never against the previous window —
    # otherwise slow drift is invisible because each window looks like the last.
    baseline: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DriftSnapshot(Base):
    """One offline drift computation for one model (ADR 0002).

    Written by the worker, read by the hot path. The gateway never computes
    these; it only ever reads the most recent row.
    """

    __tablename__ = "drift_snapshots"
    __table_args__ = (Index("ix_drift_tenant_model_time", "tenant_id", "model_id", "computed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    model_id: Mapped[str] = mapped_column(String(128), index=True)
    severity: Mapped[float] = mapped_column(Float)
    # {feature_name: {"psi": float, "ks": float, "severity": float}}
    per_feature: Mapped[dict] = mapped_column(JSON, default=dict)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DecisionLog(Base):
    """Every verdict the gateway has ever returned. Feeds the dashboard stream."""

    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decisions_tenant_time", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    model_id: Mapped[str] = mapped_column(String(128), index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    trust_score: Mapped[float] = mapped_column(Float)
    action: Mapped[str] = mapped_column(String(64), default="predict")
    trace_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditEntry(Base):
    """Tamper-evident decision log.

    ``entry_hash = SHA256(prev_hash || canonical_json(payload))``. Each entry
    commits to its predecessor, so altering any historical row invalidates
    every hash after it — which ``GET /audit/verify`` detects and localises.
    """

    __tablename__ = "audit_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "seq", name="uq_audit_tenant_seq"),
        Index("ix_audit_tenant_seq", "tenant_id", "seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    # Per-tenant monotonic sequence. Chains are per tenant so one tenant's
    # volume never affects another's verification cost.
    seq: Mapped[int] = mapped_column(Integer)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    trace_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FeatureSample(Base):
    """Raw live feature observations awaiting the next drift recompute.

    Deliberately dumb append-only storage: the hot path writes here without
    reading, and the worker drains it on its own schedule.
    """

    __tablename__ = "feature_samples"
    __table_args__ = (Index("ix_samples_tenant_model", "tenant_id", "model_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    model_id: Mapped[str] = mapped_column(String(128), index=True)
    features: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PolicyRule(Base):
    """A tenant-authored policy rule, evaluated by the policy engine."""

    __tablename__ = "policy_rules"
    __table_args__ = (Index("ix_rules_tenant", "tenant_id", "enabled"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    rule_id: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    condition: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(16), default="veto")
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
