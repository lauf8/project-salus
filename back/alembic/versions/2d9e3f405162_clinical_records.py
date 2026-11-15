from alembic import op
import sqlalchemy as sa


revision = '2d9e3f405162'
down_revision = '1c8d2e3f4051'
branch_labels = None
depends_on = None


def identity_columns():
    return [
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('astronaut_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
    ]


def audit_columns():
    return [
        sa.Column('recorded_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table('health_occurrences', *identity_columns(),
        sa.Column('icd_code', sa.String(), nullable=True),
        sa.Column('condition_name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('symptoms', sa.Text(), nullable=False),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finish_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=False), *audit_columns(),
        sa.Column('resolved_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active','recovered')", name='ck_health_occurrence_status'),
        sa.CheckConstraint("(status = 'active' AND finish_at IS NULL AND resolved_by_user_id IS NULL) OR (status = 'recovered' AND finish_at >= start_at AND resolved_by_user_id IS NOT NULL AND resolution_note IS NOT NULL)", name='ck_health_occurrence_resolution'),
    )
    op.create_table('medication_uses', *identity_columns(),
        sa.Column('medicine_id', sa.Integer(), sa.ForeignKey('medicines.id'), nullable=False),
        sa.Column('medicine_name', sa.String(), nullable=False),
        sa.Column('taken_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('instructed_by', sa.String(), nullable=False),
        sa.Column('dose', sa.String(), nullable=False),
        sa.Column('occurrence_id', sa.Integer(), sa.ForeignKey('health_occurrences.id'), nullable=True),
        *audit_columns(),
    )
    op.create_table('clinical_assessments', *identity_columns(),
        sa.Column('report', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reviewed_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name='ck_clinical_assessment_status'),
    )
    for table in ('health_occurrences', 'medication_uses', 'clinical_assessments'):
        for column in ('astronaut_id', 'mission_id'):
            op.create_index(f'ix_{table}_{column}', table, [column])


def downgrade():
    for table in ('clinical_assessments', 'medication_uses', 'health_occurrences'):
        op.drop_table(table)
