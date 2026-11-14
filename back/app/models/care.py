from datetime import date, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, Text
from sqlmodel import Field, SQLModel

from app.models.preflight import utc_now


class NutritionPlan(SQLModel, table=True):
    __tablename__ = "nutrition_plans"
    __table_args__ = (
        ForeignKeyConstraint(["mission_member_id", "mission_id"], ["mission_members.id", "mission_members.mission_id"]),
        CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="ck_nutrition_plan_period"),
        CheckConstraint("energy_target_kcal IS NULL OR energy_target_kcal > 0", name="ck_nutrition_plan_energy"),
        CheckConstraint("hydration_target_ml IS NULL OR hydration_target_ml > 0", name="ck_nutrition_plan_hydration"),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    mission_member_id: int = Field(index=True)
    author_user_id: int = Field(foreign_key="users.id")
    valid_from: date
    valid_until: date | None = None
    dietary_guidance: str = Field(sa_type=Text)
    energy_target_kcal: float | None = None
    hydration_target_ml: float | None = None
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_by_user_id: int = Field(foreign_key="users.id")


class NursingRecord(SQLModel, table=True):
    __tablename__ = "nursing_records"
    __table_args__ = (ForeignKeyConstraint(["mission_member_id", "mission_id"], ["mission_members.id", "mission_members.mission_id"]),)

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    mission_member_id: int = Field(index=True)
    author_user_id: int = Field(foreign_key="users.id")
    observed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    observations: str = Field(sa_type=Text)
    care_provided: str = Field(sa_type=Text)
    sample_collection: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_by_user_id: int = Field(foreign_key="users.id")
