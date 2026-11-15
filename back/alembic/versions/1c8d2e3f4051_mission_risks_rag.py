from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '1c8d2e3f4051'
down_revision = ('a0ef5678b920', '0b7c1d2e3f40')
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column('source_origin', sa.String(), nullable=False, server_default='NASA'),
        sa.Column('file_hash', sa.String(), nullable=True),
        sa.Column('pdf_data', sa.LargeBinary()),
        sa.Column('indexing_status', sa.String(), nullable=False, server_default='not_indexed'),
        sa.Column('indexing_error', sa.Text()),
        sa.Column('embedding_model', sa.String()),
        sa.Column('embedding_dimension', sa.Integer()),
        sa.Column('chunk_size', sa.Integer()),
        sa.Column('chunk_overlap', sa.Integer()),
        sa.Column('indexed_at', sa.DateTime(timezone=True)),
    ]:
        op.add_column('knowledge_documents', column)
    op.create_unique_constraint('uq_knowledge_documents_file_hash', 'knowledge_documents', ['file_hash'])
    op.create_index('ix_knowledge_documents_index_status', 'knowledge_documents', ['indexing_status', 'embedding_model'])
    op.add_column('knowledge_passages', sa.Column('passage_order', sa.Integer()))
    op.add_column('knowledge_passages', sa.Column('source_section', sa.String()))
    op.add_column('knowledge_passages', sa.Column('embedding', postgresql.ARRAY(sa.Float())))
    op.execute('''CREATE FUNCTION salus_cosine_similarity(a double precision[], b double precision[])
        RETURNS double precision LANGUAGE SQL IMMUTABLE STRICT PARALLEL SAFE AS $$
        SELECT CASE WHEN cardinality(a) = cardinality(b) THEN
          SUM(x * y) / NULLIF(SQRT(SUM(x * x)) * SQRT(SUM(y * y)), 0)
          ELSE NULL END FROM unnest(a, b) AS coordinates(x, y) $$''')
    op.add_column('food_stock_movements', sa.Column('risk_snapshot', sa.JSON()))
    op.create_table('mission_risk_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('planned_end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('exposure_start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('crew_size', sa.Integer(), nullable=False),
        sa.Column('consumption_window_days', sa.Integer(), nullable=False),
        sa.Column('coverage_start', sa.DateTime(timezone=True)),
        sa.Column('coverage_end', sa.DateTime(timezone=True)),
        sa.Column('inventory_complete', sa.Boolean(), nullable=False),
        sa.Column('consumption_complete', sa.Boolean(), nullable=False),
        sa.Column('daily_rates', sa.JSON(), nullable=False),
        sa.Column('approved_actions', sa.JSON(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('author_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
    )
    op.create_table('mission_occurrences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('food_product_id', sa.Integer(), sa.ForeignKey('food_products.id')),
        sa.Column('phase', sa.String(), nullable=False),
        sa.Column('event_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True)),
        sa.Column('confirmed_by_user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('author_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('source_references', sa.JSON(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('actions', sa.Text(), nullable=False),
        sa.Column('outcome', sa.Text(), nullable=False),
        sa.Column('intervention', sa.Boolean(), nullable=False),
    )
    op.create_table('mission_risk_evaluations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('rule_version', sa.String(), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('horizon', sa.DateTime(timezone=True)),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('results', sa.JSON(), nullable=False),
    )
    op.create_table('mission_risk_alerts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('risk_type', sa.String(), nullable=False),
        sa.Column('food_product_id', sa.Integer(), sa.ForeignKey('food_products.id'), nullable=False),
        sa.Column('evaluation_id', sa.Integer(), sa.ForeignKey('mission_risk_evaluations.id'), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('responsible_user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('guidance', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True)),
        sa.Column('executed_at', sa.DateTime(timezone=True)),
        sa.Column('outcome', sa.Text()),
        sa.CheckConstraint("status IN ('open', 'acknowledged', 'executed', 'resolved')", name='ck_mission_risk_status'),
    )
    op.create_index('uq_mission_risk_active', 'mission_risk_alerts', ['mission_id', 'risk_type', 'food_product_id'], unique=True, postgresql_where=sa.text("status != 'resolved'"))
    op.create_table('mission_risk_actions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('alert_id', sa.Integer(), sa.ForeignKey('mission_risk_alerts.id'), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('details', sa.Text(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    )
    for table, columns in {
        'mission_risk_plans': ['mission_id'], 'mission_occurrences': ['mission_id', 'category'],
        'mission_risk_evaluations': ['mission_id'], 'mission_risk_alerts': ['mission_id'],
        'mission_risk_actions': ['alert_id'],
    }.items():
        for column in columns:
            op.create_index(f'ix_{table}_{column}', table, [column])
    op.alter_column('health_notifications', 'alert_id', nullable=True)
    op.alter_column('health_notifications', 'observation_id', nullable=True)
    op.add_column('health_notifications', sa.Column('risk_alert_id', sa.Integer(), sa.ForeignKey('mission_risk_alerts.id')))
    op.create_unique_constraint('uq_risk_notification_recipient', 'health_notifications', ['recipient_user_id', 'mission_id', 'risk_alert_id'])


def downgrade():
    op.drop_column('food_stock_movements', 'risk_snapshot')
    op.execute('DELETE FROM health_notifications WHERE risk_alert_id IS NOT NULL')
    op.drop_constraint('uq_risk_notification_recipient', 'health_notifications')
    op.drop_column('health_notifications', 'risk_alert_id')
    op.alter_column('health_notifications', 'alert_id', nullable=False)
    op.alter_column('health_notifications', 'observation_id', nullable=False)
    for table in ['mission_risk_actions', 'mission_risk_alerts', 'mission_risk_evaluations', 'mission_occurrences', 'mission_risk_plans']:
        op.drop_table(table)
    op.execute('DROP FUNCTION salus_cosine_similarity(double precision[], double precision[])')
    for column in ['embedding', 'source_section', 'passage_order']:
        op.drop_column('knowledge_passages', column)
    op.drop_index('ix_knowledge_documents_index_status', 'knowledge_documents')
    op.drop_constraint('uq_knowledge_documents_file_hash', 'knowledge_documents')
    for column in ['indexed_at', 'chunk_overlap', 'chunk_size', 'embedding_dimension', 'embedding_model', 'indexing_error', 'indexing_status', 'pdf_data', 'file_hash', 'source_origin']:
        op.drop_column('knowledge_documents', column)
