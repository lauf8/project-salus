from alembic import op
import sqlalchemy as sa

revision = 'f37e8091a2b3'
down_revision = 'e26d7f8091a2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'exam_definitions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('exam_type_id', sa.Integer(), sa.ForeignKey('exam_types.id'), nullable=False),
        sa.Column('code', sa.String(), nullable=False, unique=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('specimen', sa.String()),
        sa.Column('preparation', sa.Text()),
        sa.Column('applicability_notes', sa.Text()),
        sa.Column('source_url', sa.String()),
        sa.Column('source_section', sa.String()),
        sa.Column('source_page', sa.Integer()),
        sa.Column('fields', sa.JSON(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('id', 'exam_type_id', name='uq_exam_definition_id_type'),
    )
    op.create_index('ix_exam_definitions_exam_type_id', 'exam_definitions', ['exam_type_id'])
    op.create_index('ix_exam_definitions_name', 'exam_definitions', ['name'])
    op.add_column('mission_exam_requirements', sa.Column('exam_definition_id', sa.Integer()))
    op.drop_constraint('uq_requirements_mission_type', 'mission_exam_requirements', type_='unique')
    op.create_index('uq_requirements_legacy_type', 'mission_exam_requirements', ['mission_id', 'exam_type_id'], unique=True, postgresql_where=sa.text('exam_definition_id IS NULL'))
    op.create_unique_constraint('uq_requirements_mission_definition', 'mission_exam_requirements', ['mission_id', 'exam_definition_id'])
    op.create_foreign_key('fk_requirement_definition_type', 'mission_exam_requirements', 'exam_definitions', ['exam_definition_id', 'exam_type_id'], ['id', 'exam_type_id'])
    op.create_index('ix_mission_exam_requirements_exam_definition_id', 'mission_exam_requirements', ['exam_definition_id'])
    op.add_column('astronaut_exams', sa.Column('definition_snapshot', sa.JSON()))
    op.add_column('exam_results', sa.Column('exam_snapshot', sa.JSON()))
    for name in ('structured_values', 'reference_ranges'):
        op.add_column('exam_results', sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
        op.alter_column('exam_results', name, server_default=None)
    for name in ('laboratory', 'performer_name', 'sample_identifier', 'method', 'report_reference'):
        op.add_column('exam_results', sa.Column(name, sa.String()))
    op.add_column('exam_results', sa.Column('collected_at', sa.DateTime(timezone=True)))


def downgrade():
    connection = op.get_bind()
    duplicates = connection.execute(sa.text('SELECT 1 FROM mission_exam_requirements GROUP BY mission_id, exam_type_id HAVING count(*) > 1 LIMIT 1')).first()
    if duplicates:
        raise RuntimeError('Multiple exams share a type in a mission; consolidate requirements before downgrading')
    for name in ('collected_at', 'report_reference', 'method', 'sample_identifier', 'performer_name', 'laboratory', 'reference_ranges', 'structured_values', 'exam_snapshot'):
        op.drop_column('exam_results', name)
    op.drop_column('astronaut_exams', 'definition_snapshot')
    op.drop_constraint('fk_requirement_definition_type', 'mission_exam_requirements', type_='foreignkey')
    op.drop_constraint('uq_requirements_mission_definition', 'mission_exam_requirements', type_='unique')
    op.drop_index('uq_requirements_legacy_type', table_name='mission_exam_requirements')
    op.drop_index('ix_mission_exam_requirements_exam_definition_id', table_name='mission_exam_requirements')
    op.drop_column('mission_exam_requirements', 'exam_definition_id')
    op.create_unique_constraint('uq_requirements_mission_type', 'mission_exam_requirements', ['mission_id', 'exam_type_id'])
    op.drop_table('exam_definitions')
