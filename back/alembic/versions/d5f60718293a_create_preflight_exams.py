from alembic import op
import sqlalchemy as sa

revision = "d5f60718293a"
down_revision = "c4e5f6071829"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("planned_launch_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("ended_at IS NULL OR (started_at IS NOT NULL AND ended_at >= started_at)", name="ck_missions_dates"),
    )
    op.create_table(
        "mission_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mission_id", sa.Integer(), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.UniqueConstraint("mission_id", "user_id", name="uq_mission_members_mission_user"),
        sa.UniqueConstraint("id", "mission_id", name="uq_mission_members_id_mission"),
        sa.CheckConstraint("role IN ('astronaut', 'flight_surgeon', 'mission_admin')", name="ck_mission_members_role"),
    )
    op.create_table(
        "exam_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "mission_exam_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mission_id", sa.Integer(), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("exam_type_id", sa.Integer(), sa.ForeignKey("exam_types.id"), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("due_days_before_launch", sa.Integer(), nullable=False),
        sa.UniqueConstraint("mission_id", "exam_type_id", name="uq_requirements_mission_type"),
        sa.UniqueConstraint("id", "mission_id", name="uq_requirements_id_mission"),
        sa.CheckConstraint("due_days_before_launch >= 0", name="ck_requirements_due_days"),
    )
    op.create_table(
        "astronaut_exams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mission_id", sa.Integer(), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("mission_member_id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mission_member_id", "requirement_id", name="uq_astronaut_exams_member_requirement"),
        sa.ForeignKeyConstraint(["mission_member_id", "mission_id"], ["mission_members.id", "mission_members.mission_id"], name="fk_astronaut_exams_member_mission"),
        sa.ForeignKeyConstraint(["requirement_id", "mission_id"], ["mission_exam_requirements.id", "mission_exam_requirements.mission_id"], name="fk_astronaut_exams_requirement_mission"),
    )
    op.create_table(
        "exam_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("astronaut_exam_id", sa.Integer(), sa.ForeignKey("astronaut_exams.id"), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
    )
    op.create_table(
        "exam_result_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exam_result_id", sa.Integer(), sa.ForeignKey("exam_results.id"), nullable=False),
        sa.Column("reviewer_member_id", sa.Integer(), sa.ForeignKey("mission_members.id"), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('accepted', 'repeat_requested')", name="ck_exam_result_reviews_decision"),
    )
    for table, columns in {
        "mission_members": ["mission_id", "user_id"],
        "mission_exam_requirements": ["mission_id", "exam_type_id"],
        "astronaut_exams": ["mission_id", "mission_member_id", "requirement_id"],
        "exam_results": ["astronaut_exam_id", "recorded_by_user_id"],
        "exam_result_reviews": ["exam_result_id", "reviewer_member_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in (
        "exam_result_reviews", "exam_results", "astronaut_exams",
        "mission_exam_requirements", "exam_types", "mission_members", "missions",
    ):
        op.drop_table(table)
