"""Preserve previous automatic runs when engine and interpretation change."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("automatic_runs")
    previous_name = next(
        (
            item["name"] or "uq_automatic_runs_file_id"
            for item in constraints
            if item["column_names"] == ["file_id"]
        ),
        "uq_automatic_runs_file_id",
    )
    with op.batch_alter_table(
        "automatic_runs", naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}
    ) as batch:
        batch.add_column(
            sa.Column("version", sa.String(30), nullable=False, server_default="automatic-1")
        )
        batch.drop_constraint(previous_name, type_="unique")
        batch.create_unique_constraint("uq_automatic_runs_file_version", ["file_id", "version"])


def downgrade():
    # Preserve runs: an older schema cannot represent multiple versions of a file.
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text("SELECT file_id FROM automatic_runs GROUP BY file_id HAVING COUNT(*) > 1 LIMIT 1")
    ).first()
    if duplicate:
        raise RuntimeError("Multiple workflow versions exist; downgrade would lose history.")
    with op.batch_alter_table("automatic_runs") as batch:
        batch.drop_constraint("uq_automatic_runs_file_version", type_="unique")
        batch.create_unique_constraint("uq_automatic_runs_file_id", ["file_id"])
        batch.drop_column("version")
