from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, JSON, Numeric, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Spacecraft(SQLModel, table=True):
    __tablename__ = 'spacecraft'
    __table_args__ = (
        CheckConstraint("status IN ('available', 'in_use')", name="ck_spacecraft_status"),
        CheckConstraint('length(trim(name)) > 0', name='ck_spacecraft_name'),
        CheckConstraint('manufactured_year > 0', name='ck_spacecraft_year'),
        CheckConstraint('maximum_crew_capacity > 0', name='ck_spacecraft_capacity'),
    )

    id: int | None = Field(default=None, primary_key=True)
    status: str = Field(default="available")
    name: str = Field(sa_type=Text, index=True)
    maximum_crew_capacity: int | None = None
    model: str | None = Field(default=None, sa_type=Text)
    manufacturer: str | None = Field(default=None, sa_type=Text)
    serial_number: str | None = Field(default=None, sa_type=Text)
    manufactured_year: int | None = Field(default=None, sa_type=SmallInteger)
    description: str | None = Field(default=None, sa_type=Text)
    technical_reference_url: str | None = Field(default=None, sa_type=Text)


class SpacecraftModule(SQLModel, table=True):
    __tablename__ = 'spacecraft_modules'
    __table_args__ = (
        UniqueConstraint('spacecraft_id', 'code', name='uq_spacecraft_modules_spacecraft_code'),
        CheckConstraint('length(trim(code)) > 0', name='ck_spacecraft_modules_code'),
        CheckConstraint('length(trim(name)) > 0', name='ck_spacecraft_modules_name'),
        CheckConstraint('manufactured_year > 0', name='ck_spacecraft_modules_year'),
        CheckConstraint('pressurized_volume_m3 > 0', name='ck_spacecraft_modules_volume'),
    )

    id: int | None = Field(default=None, primary_key=True)
    spacecraft_id: int = Field(sa_column=Column(Integer, ForeignKey('spacecraft.id', ondelete='RESTRICT'), nullable=False, index=True))
    code: str = Field(sa_type=Text)
    name: str = Field(sa_type=Text, index=True)
    purpose: str | None = Field(default=None, sa_type=Text)
    manufacturer: str | None = Field(default=None, sa_type=Text)
    serial_number: str | None = Field(default=None, sa_type=Text)
    manufactured_year: int | None = Field(default=None, sa_type=SmallInteger)
    is_pressurized: bool | None = None
    is_habitable: bool | None = None
    pressurized_volume_m3: Decimal | None = Field(default=None, sa_column=Column(Numeric))
    technical_specifications: dict | None = Field(default=None, sa_column=Column(JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), 'postgresql')))
    technical_reference_url: str | None = Field(default=None, sa_type=Text)
