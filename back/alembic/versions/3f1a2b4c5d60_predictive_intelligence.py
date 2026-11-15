from alembic import op
import sqlalchemy as sa


revision = '3f1a2b4c5d60'
down_revision = '2d9e3f405162'
branch_labels = None
depends_on = None


def timestamp(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    op.create_table(
        'prediction_models',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('subject_type', sa.String(), nullable=False),
        sa.Column('risk_type', sa.Text(), nullable=False),
        sa.Column('version', sa.Text(), nullable=False),
        sa.Column('predicted_outcome', sa.Text(), nullable=False),
        sa.Column('horizon_hours', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('validation_metrics', sa.JSON(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.Column('artifact', sa.LargeBinary(), nullable=True),
        sa.Column('artifact_sha256', sa.String(), nullable=True),
        timestamp('trained_at', True), timestamp('activated_at', True),
        sa.Column('approved_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        timestamp('created_at'),
        sa.UniqueConstraint('name', 'version', name='uq_prediction_models_name_version'),
        sa.CheckConstraint("kind IN ('rule', 'anomaly', 'supervised')", name='ck_prediction_models_kind'),
        sa.CheckConstraint("status IN ('candidate', 'rejected', 'approved', 'active', 'retired')", name='ck_prediction_models_status'),
        sa.CheckConstraint("subject_type IN ('astronaut', 'mission', 'spacecraft')", name='ck_prediction_models_subject'),
    )
    op.create_index('ix_prediction_models_name', 'prediction_models', ['name'])
    op.create_index('uq_prediction_models_active_name', 'prediction_models', ['name'], unique=True, postgresql_where=sa.text("status = 'active'"))

    op.create_table(
        'feature_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subject_type', sa.String(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=True),
        timestamp('as_of'),
        sa.Column('feature_set_version', sa.String(), nullable=False),
        sa.Column('input_fingerprint', sa.String(), nullable=False),
        sa.Column('features', sa.JSON(), nullable=False),
        sa.Column('quality', sa.JSON(), nullable=False),
        sa.Column('source_references', sa.JSON(), nullable=False),
        timestamp('created_at'),
        sa.UniqueConstraint('subject_type', 'subject_id', 'as_of', 'feature_set_version', 'input_fingerprint', name='uq_feature_snapshots_input'),
        sa.CheckConstraint("subject_type IN ('astronaut', 'mission', 'spacecraft')", name='ck_feature_snapshots_subject'),
    )
    op.create_index('ix_feature_snapshots_mission_id', 'feature_snapshots', ['mission_id'])
    op.create_index('ix_feature_snapshots_subject_time', 'feature_snapshots', ['subject_type', 'subject_id', 'as_of'])

    op.create_table(
        'prediction_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subject_type', sa.String(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=True),
        timestamp('as_of'),
        sa.Column('horizon_hours', sa.Integer(), nullable=True),
        sa.Column('feature_snapshot_id', sa.Integer(), sa.ForeignKey('feature_snapshots.id'), nullable=True),
        sa.Column('model_versions', sa.JSON(), nullable=False),
        sa.Column('engine_version', sa.String(), nullable=False),
        sa.Column('trigger', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('idempotency_key', sa.String(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('requested_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        timestamp('started_at'), timestamp('finished_at', True),
        sa.UniqueConstraint('idempotency_key', name='uq_prediction_runs_idempotency'),
        sa.CheckConstraint("subject_type IN ('astronaut', 'mission', 'spacecraft')", name='ck_prediction_runs_subject'),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name='ck_prediction_runs_status'),
        sa.CheckConstraint("trigger IN ('manual', 'scheduled', 'new_data')", name='ck_prediction_runs_trigger'),
    )
    op.create_index('ix_prediction_runs_mission_id', 'prediction_runs', ['mission_id'])
    op.create_index('ix_prediction_runs_subject_time', 'prediction_runs', ['subject_type', 'subject_id', 'as_of'])

    op.create_table(
        'risk_predictions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('prediction_runs.id'), nullable=False),
        sa.Column('model_id', sa.Integer(), sa.ForeignKey('prediction_models.id'), nullable=True),
        sa.Column('domain', sa.String(), nullable=False),
        sa.Column('risk_type', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('prediction_kind', sa.String(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('score_meaning', sa.Text(), nullable=True),
        sa.Column('calibrated_probability', sa.Float(), nullable=True),
        sa.Column('risk_level', sa.String(), nullable=False),
        sa.Column('horizon_hours', sa.Integer(), nullable=True),
        sa.Column('factors', sa.JSON(), nullable=False),
        sa.Column('data_quality', sa.JSON(), nullable=False),
        sa.Column('uncertainty', sa.JSON(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('explanation', sa.JSON(), nullable=False),
        timestamp('created_at'),
        sa.CheckConstraint("prediction_kind IN ('rule', 'anomaly', 'ml', 'insufficient_data')", name='ck_risk_predictions_kind'),
        sa.CheckConstraint("risk_level IN ('none', 'low', 'moderate', 'high', 'undetermined')", name='ck_risk_predictions_level'),
        sa.CheckConstraint('calibrated_probability IS NULL OR (calibrated_probability >= 0 AND calibrated_probability <= 1)', name='ck_risk_predictions_probability'),
        sa.CheckConstraint("calibrated_probability IS NULL OR prediction_kind = 'ml'", name='ck_risk_predictions_probability_kind'),
    )
    op.create_index('ix_risk_predictions_run_id', 'risk_predictions', ['run_id'])
    op.create_index('ix_risk_predictions_run_type', 'risk_predictions', ['run_id', 'risk_type'])

    op.create_table(
        'recommendation_actions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('risk_types', sa.JSON(), nullable=False),
        sa.Column('action_category', sa.String(), nullable=False),
        sa.Column('responsible_roles', sa.JSON(), nullable=False),
        sa.Column('eligibility', sa.JSON(), nullable=False),
        sa.Column('contraindications', sa.JSON(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('evidence_quality', sa.String(), nullable=False),
        sa.Column('feasibility', sa.Float(), nullable=False),
        sa.Column('source_references', sa.JSON(), nullable=False),
        sa.Column('rag_query', sa.Text(), nullable=True),
        sa.Column('approval_status', sa.String(), nullable=False),
        sa.Column('approved_by', sa.Text(), nullable=True),
        timestamp('created_at'),
        sa.UniqueConstraint('code', 'version', name='uq_recommendation_actions_code_version'),
        sa.CheckConstraint("approval_status IN ('draft', 'approved', 'retired')", name='ck_recommendation_actions_approval'),
        sa.CheckConstraint("action_category IN ('clinical_review', 'monitoring', 'operational', 'psychological_support', 'nutrition_review')", name='ck_recommendation_actions_category'),
        sa.CheckConstraint('priority BETWEEN 1 AND 5', name='ck_recommendation_actions_priority'),
    )

    op.create_table(
        'recommendation_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('prediction_id', sa.Integer(), sa.ForeignKey('risk_predictions.id'), nullable=False),
        sa.Column('action_id', sa.Integer(), sa.ForeignKey('recommendation_actions.id'), nullable=False),
        sa.Column('subject_type', sa.String(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('rank_score', sa.Float(), nullable=False),
        sa.Column('ranking', sa.JSON(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('urgency', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('decided_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        timestamp('decided_at', True),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('explanation', sa.JSON(), nullable=False),
        timestamp('created_at'), timestamp('updated_at'),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'executed', 'superseded')", name='ck_recommendation_events_status'),
        sa.CheckConstraint("subject_type IN ('astronaut', 'mission', 'spacecraft')", name='ck_recommendation_events_subject'),
    )
    op.create_index('ix_recommendation_events_prediction_id', 'recommendation_events', ['prediction_id'])
    op.create_index('ix_recommendation_events_mission_status', 'recommendation_events', ['mission_id', 'status'])
    op.create_index('uq_recommendation_events_open', 'recommendation_events', ['subject_type', 'subject_id', 'action_id'], unique=True, postgresql_where=sa.text("status IN ('pending', 'accepted')"))

    op.create_table(
        'recommendation_feedback',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('recommendation_id', sa.Integer(), sa.ForeignKey('recommendation_events.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('decision', sa.String(), nullable=False),
        sa.Column('justification', sa.Text(), nullable=False),
        sa.Column('executed_action', sa.Text(), nullable=True),
        timestamp('created_at'),
        sa.CheckConstraint("decision IN ('accepted', 'rejected', 'executed')", name='ck_recommendation_feedback_decision'),
    )
    op.create_index('ix_recommendation_feedback_recommendation_id', 'recommendation_feedback', ['recommendation_id'])

    op.create_table(
        'recommendation_outcomes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('recommendation_id', sa.Integer(), sa.ForeignKey('recommendation_events.id'), nullable=False),
        sa.Column('indicator', sa.String(), nullable=False),
        sa.Column('value_before', sa.Float(), nullable=True),
        sa.Column('value_after', sa.Float(), nullable=True),
        sa.Column('observation_window_hours', sa.Integer(), nullable=False),
        sa.Column('result', sa.String(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('recorded_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        timestamp('evaluated_at'),
        sa.CheckConstraint("result IN ('improved', 'unchanged', 'worsened', 'inconclusive')", name='ck_recommendation_outcomes_result'),
        sa.CheckConstraint('observation_window_hours > 0', name='ck_recommendation_outcomes_window'),
    )
    op.create_index('ix_recommendation_outcomes_recommendation_id', 'recommendation_outcomes', ['recommendation_id'])


def downgrade():
    for table in ('recommendation_outcomes', 'recommendation_feedback', 'recommendation_events', 'recommendation_actions',
                  'risk_predictions', 'prediction_runs', 'feature_snapshots', 'prediction_models'):
        op.drop_table(table)
