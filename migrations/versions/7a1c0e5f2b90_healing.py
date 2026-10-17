"""governed self-healing: incidents and remediations

Revision ID: 7a1c0e5f2b90
Revises: 5d338ec84d26
Create Date: 2026-10-17 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "7a1c0e5f2b90"
down_revision = "5d338ec84d26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("diagnosis", sa.JSON(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_tenant_id", "incidents", ["tenant_id"])
    op.create_index("ix_incidents_model_id", "incidents", ["model_id"])
    op.create_index("ix_incidents_tenant_model", "incidents", ["tenant_id", "model_id", "status"])

    op.create_table(
        "remediations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("shadow", sa.JSON(), nullable=False),
        sa.Column("undo", sa.JSON(), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_remediations_tenant_id", "remediations", ["tenant_id"])
    op.create_index("ix_remediations_model_id", "remediations", ["model_id"])
    op.create_index("ix_remediations_incident", "remediations", ["incident_id"])


def downgrade() -> None:
    op.drop_table("remediations")
    op.drop_table("incidents")
