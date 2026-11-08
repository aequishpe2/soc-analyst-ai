"""Durable automatic upload-to-dashboard workflow."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_ai_drafts_pending", "ai_drafts", ["status", "created_at", "id"])
    op.create_table(
        "automatic_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "file_id", sa.String(36), sa.ForeignKey("source_files.id"), nullable=False, unique=True
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("phase", sa.String(30), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("automatic_runs")
    op.drop_index("ix_ai_drafts_pending", table_name="ai_drafts")
