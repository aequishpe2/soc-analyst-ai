"""Persist bounded local AI drafts separately from deterministic findings."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "finding_id", sa.String(36), sa.ForeignKey("findings.id"), unique=True, nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("model_digest", sa.String(100)),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("input_hash", sa.String(64)),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("ai_drafts")
