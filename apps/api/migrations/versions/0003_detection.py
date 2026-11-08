"""Versioned analysis scopes, findings, groups and event references."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "config_hash"),
    )
    op.create_index("ix_analyses_case_id", "analyses", ["case_id"])
    op.create_table(
        "analysis_scopes",
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("analyses.id"), primary_key=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("import_runs.id"), primary_key=True),
    )
    op.create_table(
        "investigation_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("analyses.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_investigation_groups_analysis_id", "investigation_groups", ["analysis_id"])
    op.create_table(
        "findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("analyses.id"), nullable=False),
        sa.Column(
            "group_id", sa.String(36), sa.ForeignKey("investigation_groups.id"), nullable=False
        ),
        sa.Column("rule_id", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    for column in ("analysis_id", "group_id", "severity"):
        op.create_index(f"ix_findings_{column}", "findings", [column])
    op.create_table(
        "finding_evidence",
        sa.Column("finding_id", sa.String(36), sa.ForeignKey("findings.id"), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("events.id"), primary_key=True),
        sa.Column("role", sa.String(30), nullable=False),
    )
    op.create_table(
        "analysis_duplicates",
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("analyses.id"), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("events.id"), primary_key=True),
        sa.Column("representative_id", sa.String(36), sa.ForeignKey("events.id"), nullable=False),
    )


def downgrade():
    for name in (
        "analysis_duplicates",
        "finding_evidence",
        "findings",
        "investigation_groups",
        "analysis_scopes",
        "analyses",
    ):
        op.drop_table(name)
