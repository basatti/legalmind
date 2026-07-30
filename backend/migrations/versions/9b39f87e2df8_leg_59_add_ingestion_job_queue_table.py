from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '9b39f87e2df8'
down_revision: Union[str, Sequence[str], None] = '09108df8f690'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ingestionjob',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'running', 'done', 'failed', name='ingestionstatus'),
            nullable=False,
        ),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['document.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ingestionjob_status_id', 'ingestionjob', ['status', 'id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_ingestionjob_status_id', table_name='ingestionjob')
    op.drop_table('ingestionjob')
    sa.Enum(name='ingestionstatus').drop(op.get_bind(), checkfirst=True)
