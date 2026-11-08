"""Keep unqualified file times without assigning an invented UTC offset."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("file_timestamp", sa.String(40), nullable=True))


def downgrade():
    with op.batch_alter_table("events") as batch:
        batch.drop_column("file_timestamp")
