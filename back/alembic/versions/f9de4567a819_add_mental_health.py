from alembic import op
import sqlalchemy as sa


revision = 'f9de4567a819'
down_revision = 'e8cd3456f708'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_psychologist", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_constraint('ck_mission_members_role', 'mission_members', type_='check')
    op.create_check_constraint('ck_mission_members_role', 'mission_members', "role IN ('astronaut', 'flight_surgeon', 'mission_admin', 'psychologist')")
    op.execute("""CREATE TABLE mental_health_check_ins (
	id SERIAL NOT NULL,
	mission_id INTEGER NOT NULL,
	mission_member_id INTEGER NOT NULL,
	check_in_date DATE NOT NULL,
	happiness_level INTEGER NOT NULL,
	satisfaction_level INTEGER NOT NULL,
	stress_level INTEGER,
	energy_level INTEGER,
	sleep_quality INTEGER,
	workload_level INTEGER,
	isolation_level INTEGER,
	crew_connection_level INTEGER,
	notes TEXT,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_by_user_id INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_mental_check_in_day UNIQUE (mission_member_id, check_in_date),
	FOREIGN KEY(mission_member_id, mission_id) REFERENCES mission_members (id, mission_id),
	CONSTRAINT ck_mental_happiness_level CHECK (happiness_level BETWEEN 1 AND 5),
	CONSTRAINT ck_mental_satisfaction_level CHECK (satisfaction_level BETWEEN 1 AND 5),
	CONSTRAINT ck_mental_stress_level CHECK (stress_level BETWEEN 1 AND 5),
	CONSTRAINT ck_mental_energy_level CHECK (energy_level BETWEEN 1 AND 5),
	CONSTRAINT ck_mental_sleep_quality CHECK (sleep_quality BETWEEN 1 AND 5),
	CONSTRAINT ck_mental_workload_level CHECK (workload_level BETWEEN 1 AND 5),
	CONSTRAINT ck_mental_isolation_level CHECK (isolation_level BETWEEN 1 AND 5),
	CONSTRAINT ck_mental_crew_connection_level CHECK (crew_connection_level BETWEEN 1 AND 5),
	FOREIGN KEY(mission_id) REFERENCES missions (id),
	FOREIGN KEY(updated_by_user_id) REFERENCES users (id)
)""")
    op.execute("""CREATE INDEX ix_mental_health_check_ins_mission_member_id ON mental_health_check_ins (mission_member_id)""")
    op.execute("""CREATE INDEX ix_mental_health_check_ins_mission_id ON mental_health_check_ins (mission_id)""")
    op.execute("""CREATE TABLE psychology_contact_requests (
	id SERIAL NOT NULL,
	mission_id INTEGER NOT NULL,
	mission_member_id INTEGER NOT NULL,
	author_user_id INTEGER NOT NULL,
	status VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_by_user_id INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(mission_member_id, mission_id) REFERENCES mission_members (id, mission_id),
	CONSTRAINT uq_psychology_request_scope UNIQUE (id, mission_member_id, mission_id),
	CONSTRAINT ck_psychology_request_status CHECK (status IN ('pending', 'fulfilled')),
	FOREIGN KEY(mission_id) REFERENCES missions (id),
	FOREIGN KEY(author_user_id) REFERENCES users (id),
	FOREIGN KEY(updated_by_user_id) REFERENCES users (id)
)""")
    op.execute("""CREATE UNIQUE INDEX uq_psychology_pending_request ON psychology_contact_requests (mission_member_id) WHERE status = 'pending'""")
    op.execute("""CREATE INDEX ix_psychology_contact_requests_mission_id ON psychology_contact_requests (mission_id)""")
    op.execute("""CREATE TABLE psychology_follow_ups (
	id SERIAL NOT NULL,
	mission_id INTEGER NOT NULL,
	mission_member_id INTEGER NOT NULL,
	psychologist_user_id INTEGER NOT NULL,
	contact_request_id INTEGER,
	session_at TIMESTAMP WITH TIME ZONE NOT NULL,
	review_period_start DATE NOT NULL,
	review_period_end DATE NOT NULL,
	session_summary TEXT NOT NULL,
	agreed_actions TEXT,
	next_follow_up_on DATE,
	private_notes TEXT,
	share_agreed_actions BOOLEAN NOT NULL,
	share_next_follow_up BOOLEAN NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_by_user_id INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(mission_member_id, mission_id) REFERENCES mission_members (id, mission_id),
	FOREIGN KEY(contact_request_id, mission_member_id, mission_id) REFERENCES psychology_contact_requests (id, mission_member_id, mission_id),
	CONSTRAINT ck_psychology_review_period CHECK (review_period_start <= review_period_end),
	CONSTRAINT uq_psychology_session_request UNIQUE (contact_request_id),
	FOREIGN KEY(mission_id) REFERENCES missions (id),
	FOREIGN KEY(psychologist_user_id) REFERENCES users (id),
	FOREIGN KEY(updated_by_user_id) REFERENCES users (id)
)""")
    op.execute("""CREATE INDEX ix_psychology_follow_ups_mission_member_id ON psychology_follow_ups (mission_member_id)""")
    op.execute("""CREATE INDEX ix_psychology_follow_ups_mission_id ON psychology_follow_ups (mission_id)""")
    op.execute("""CREATE TABLE mental_health_audit_events (
	id SERIAL NOT NULL,
	mission_id INTEGER NOT NULL,
	actor_user_id INTEGER NOT NULL,
	resource_type VARCHAR NOT NULL,
	resource_id INTEGER NOT NULL,
	action VARCHAR NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(mission_id) REFERENCES missions (id),
	FOREIGN KEY(actor_user_id) REFERENCES users (id)
)""")
    op.execute("""CREATE INDEX ix_mental_health_audit_events_mission_id ON mental_health_audit_events (mission_id)""")


def downgrade():
    op.drop_column("users", "is_psychologist")
    op.drop_table('mental_health_audit_events')
    op.drop_table('psychology_follow_ups')
    op.drop_table('psychology_contact_requests')
    op.drop_table('mental_health_check_ins')
    op.drop_constraint('ck_mission_members_role', 'mission_members', type_='check')
    op.create_check_constraint('ck_mission_members_role', 'mission_members', "role IN ('astronaut', 'flight_surgeon', 'mission_admin')")

