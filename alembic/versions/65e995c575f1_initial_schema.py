"""initial schema

Revision ID: 65e995c575f1
Revises: 
Create Date: 2026-05-24 19:32:10.562948

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65e995c575f1'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS faers")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS faers CASCADE")
