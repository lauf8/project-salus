import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = 'a48f9012b3c4'
down_revision = 'f37e8091a2b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'spacecraft',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('model', sa.Text()),
        sa.Column('manufacturer', sa.Text()),
        sa.Column('serial_number', sa.Text()),
        sa.Column('manufactured_year', sa.SmallInteger()),
        sa.Column('description', sa.Text()),
        sa.Column('technical_reference_url', sa.Text()),
        sa.CheckConstraint('length(trim(name)) > 0', name='ck_spacecraft_name'),
        sa.CheckConstraint('manufactured_year > 0', name='ck_spacecraft_year'),
    )
    op.create_index('ix_spacecraft_name', 'spacecraft', ['name'])
    op.create_table(
        'spacecraft_modules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('spacecraft_id', sa.Integer(), sa.ForeignKey('spacecraft.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('code', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('purpose', sa.Text()),
        sa.Column('manufacturer', sa.Text()),
        sa.Column('serial_number', sa.Text()),
        sa.Column('manufactured_year', sa.SmallInteger()),
        sa.Column('is_pressurized', sa.Boolean()),
        sa.Column('is_habitable', sa.Boolean()),
        sa.Column('pressurized_volume_m3', sa.Numeric()),
        sa.Column('technical_specifications', postgresql.JSONB(none_as_null=True)),
        sa.Column('technical_reference_url', sa.Text()),
        sa.UniqueConstraint('spacecraft_id', 'code', name='uq_spacecraft_modules_spacecraft_code'),
        sa.CheckConstraint('length(trim(code)) > 0', name='ck_spacecraft_modules_code'),
        sa.CheckConstraint('length(trim(name)) > 0', name='ck_spacecraft_modules_name'),
        sa.CheckConstraint('manufactured_year > 0', name='ck_spacecraft_modules_year'),
        sa.CheckConstraint('pressurized_volume_m3 > 0', name='ck_spacecraft_modules_volume'),
    )
    op.create_index('ix_spacecraft_modules_spacecraft_id', 'spacecraft_modules', ['spacecraft_id'])
    op.create_index('ix_spacecraft_modules_name', 'spacecraft_modules', ['name'])


def downgrade():
    op.drop_table('spacecraft_modules')
    op.drop_table('spacecraft')
