"""Immutable sources, durable local jobs and traceable events."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # Freeze this migration independently of future model additions.
    import sqlalchemy as sa

    op.create_table(
        "source_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("extension", sa.String(8), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("options_hash", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=True),
        sa.Column("rows_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "sha256", "options_hash"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "import_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("file_id", sa.String(36), sa.ForeignKey("source_files.id"), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("file_id", "config_hash"),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("import_runs.id"), nullable=False),
        sa.Column("sheet", sa.String(100), nullable=False),
        sa.Column("row", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("timestamp_utc", sa.String(40), nullable=True),
        sa.Column("normalized", sa.JSON(), nullable=False),
        sa.Column("original", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
    )
    op.create_table(
        "row_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("import_id", sa.String(36), sa.ForeignKey("import_runs.id"), nullable=False),
        sa.Column("sheet", sa.String(100), nullable=False),
        sa.Column("row", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
    )
    for table, columns in {
        "source_files": ["case_id"],
        "jobs": ["file_id"],
        "import_runs": ["file_id"],
        "events": ["case_id", "import_id"],
        "row_issues": ["import_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for name in ["row_issues", "events", "import_runs", "jobs", "source_files"]:
        op.drop_table(name)
