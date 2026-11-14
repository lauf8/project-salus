from pydantic import ConfigDict, EmailStr, Field, model_validator
from sqlmodel import SQLModel

from app.core.roles import PROFILE_FIELDS, PUBLIC_PROFILE_FIELDS


class UserCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    password_confirmation: str = Field(min_length=6, max_length=72)
    address: str | None = None
    phone: str | None = None
    is_astronaut: bool = True
    is_physician: bool = False
    is_psychologist: bool = False
    is_nutritionist: bool = False
    is_nurse: bool = False
    is_observer: bool = False
    is_mission_admin: bool = False

    @model_validator(mode="after")
    def validate_registration(self):
        if not any(getattr(self, name) for name in PUBLIC_PROFILE_FIELDS):
            raise ValueError("Select at least one account profile")
        if self.password != self.password_confirmation:
            raise ValueError("Password confirmation does not match")
        return self


class UserResponse(SQLModel):
    is_astronaut: bool = False
    is_physician: bool = False
    is_psychologist: bool = False
    is_nutritionist: bool = False
    is_nurse: bool = False
    is_observer: bool = False
    is_mission_admin: bool = False
    is_global_admin: bool = False
    is_active: bool = True
    id: int
    name: str
    email: str
    phone: str | None = None
    address: str | None = None


class UserProfilesUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")
    is_astronaut: bool
    is_physician: bool
    is_psychologist: bool
    is_nutritionist: bool
    is_nurse: bool
    is_observer: bool
    is_mission_admin: bool
    is_global_admin: bool
    is_active: bool

    @model_validator(mode="after")
    def validate_profiles(self):
        if not any(getattr(self, name) for name in PROFILE_FIELDS):
            raise ValueError("At least one profile is required")
        return self


class PaginationMeta(SQLModel):
    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedUsersResponse(SQLModel):
    data: list[UserResponse]
    pagination: PaginationMeta
