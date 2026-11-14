from sqlalchemy import CheckConstraint, Text
from sqlmodel import Field, SQLModel


class Medicine(SQLModel, table=True):
    __tablename__ = 'medicines'
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name='ck_medicines_name'),)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200, index=True)
    main_indications: str | None = Field(default=None, sa_type=Text)


class ActiveIngredient(SQLModel, table=True):
    __tablename__ = 'active_ingredients'
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name='ck_active_ingredients_name'),)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200, index=True)


class MedicineActiveIngredient(SQLModel, table=True):
    __tablename__ = 'medicine_active_ingredients'

    medicine_id: int = Field(foreign_key='medicines.id', primary_key=True)
    active_ingredient_id: int = Field(foreign_key='active_ingredients.id', primary_key=True, index=True)


class CrewMemberAllergy(SQLModel, table=True):
    __tablename__ = 'crew_member_allergies'

    crew_member_id: int = Field(foreign_key='users.id', primary_key=True)
    active_ingredient_id: int = Field(foreign_key='active_ingredients.id', primary_key=True, index=True)
