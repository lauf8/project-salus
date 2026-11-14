from alembic import op
import sqlalchemy as sa


revision = 'a8293b4c5d6e'
down_revision = 'f718293a4b5c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('allergy_screening_completed', sa.Boolean(), nullable=False, server_default=sa.false()))
    for table in ('medicines', 'active_ingredients'):
        op.create_table(table,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(200), nullable=False),
            sa.CheckConstraint('length(trim(name)) > 0', name=f'ck_{table}_name'),
        )
        op.create_index(f'ix_{table}_name', table, ['name'])
    op.create_table('medicine_active_ingredients',
        sa.Column('medicine_id', sa.Integer(), sa.ForeignKey('medicines.id'), primary_key=True),
        sa.Column('active_ingredient_id', sa.Integer(), sa.ForeignKey('active_ingredients.id'), primary_key=True),
    )
    op.create_table('crew_member_allergies',
        sa.Column('crew_member_id', sa.Integer(), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('active_ingredient_id', sa.Integer(), sa.ForeignKey('active_ingredients.id'), primary_key=True),
    )
    for table in ('medicine_active_ingredients', 'crew_member_allergies'):
        op.create_index(f'ix_{table}_active_ingredient_id', table, ['active_ingredient_id'])


def downgrade():
    op.drop_table('crew_member_allergies')
    op.drop_table('medicine_active_ingredients')
    op.drop_table('active_ingredients')
    op.drop_table('medicines')
    op.drop_column('users', 'allergy_screening_completed')
