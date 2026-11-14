from alembic import op
import sqlalchemy as sa


revision = 'e26d7f8091a2'
down_revision = 'd15c6e7f8091'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('health_notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('recipient_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('mission_id', sa.Integer(), sa.ForeignKey('missions.id'), nullable=False),
        sa.Column('alert_id', sa.Integer(), sa.ForeignKey('health_alerts.id'), nullable=False),
        sa.Column('observation_id', sa.Integer(), sa.ForeignKey('health_observations.id'), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('recipient_user_id', 'mission_id', 'alert_id', name='uq_health_notification_recipient_mission_alert'),
    )
    op.create_index('ix_health_notification_inbox', 'health_notifications', ['recipient_user_id', 'read_at', 'created_at', 'id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM health_notifications)')).scalar():
        raise RuntimeError('Preserve o histórico de notificações antes de reverter esta migration')
    op.drop_table('health_notifications')
