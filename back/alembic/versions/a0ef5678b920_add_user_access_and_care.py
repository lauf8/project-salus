from alembic import op
import sqlalchemy as sa


revision = "a0ef5678b920"
down_revision = "f9a1b2c3d4e5"
branch_labels = None
depends_on = None


PROFILE_COLUMNS = ("is_nutritionist", "is_nurse", "is_observer", "is_mission_admin", "is_global_admin", "is_active")


def upgrade():
    for name in PROFILE_COLUMNS:
        op.add_column("users", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true() if name == "is_active" else sa.false()))
    op.execute("UPDATE users SET is_mission_admin = true WHERE id IN (SELECT user_id FROM mission_members WHERE role = 'mission_admin')")
    op.drop_constraint("ck_mission_members_role", "mission_members", type_="check")
    op.create_check_constraint("ck_mission_members_role", "mission_members", "role IN ('astronaut', 'flight_surgeon', 'mission_admin', 'psychologist', 'nutritionist', 'nurse', 'observer')")
    op.create_table("access_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_access_audit_events_actor_user_id", "access_audit_events", ["actor_user_id"])
    op.create_table("nutrition_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mission_id", sa.Integer(), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("mission_member_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date()),
        sa.Column("dietary_guidance", sa.Text(), nullable=False),
        sa.Column("energy_target_kcal", sa.Float()),
        sa.Column("hydration_target_ml", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.ForeignKeyConstraint(["mission_member_id", "mission_id"], ["mission_members.id", "mission_members.mission_id"]),
        sa.CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="ck_nutrition_plan_period"),
        sa.CheckConstraint("energy_target_kcal IS NULL OR energy_target_kcal > 0", name="ck_nutrition_plan_energy"),
        sa.CheckConstraint("hydration_target_ml IS NULL OR hydration_target_ml > 0", name="ck_nutrition_plan_hydration"),
    )
    op.create_table("nursing_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mission_id", sa.Integer(), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("mission_member_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observations", sa.Text(), nullable=False),
        sa.Column("care_provided", sa.Text(), nullable=False),
        sa.Column("sample_collection", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.ForeignKeyConstraint(["mission_member_id", "mission_id"], ["mission_members.id", "mission_members.mission_id"]),
    )
    for table in ("nutrition_plans", "nursing_records"):
        for column in ("mission_id", "mission_member_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    op.drop_table("nursing_records")
    op.drop_table("nutrition_plans")
    op.drop_table("access_audit_events")
    op.drop_constraint("ck_mission_members_role", "mission_members", type_="check")
    op.create_check_constraint("ck_mission_members_role", "mission_members", "role IN ('astronaut', 'flight_surgeon', 'mission_admin', 'psychologist')")
    for name in reversed(PROFILE_COLUMNS):
        op.drop_column("users", name)
