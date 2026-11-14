from sqlmodel import SQLModel
from pydantic import EmailStr, model_validator, Field


class UserCreate(SQLModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    password_confirmation: str = Field(min_length=6, max_length=72)
    address: str | None = None
    phone: str | None = None
    is_astronaut: bool = True
    is_physician: bool = False

    @model_validator(mode="after")
    def validate_password_confirmation(self):
        if not (self.is_astronaut or self.is_physician):
            raise ValueError("Selecione ao menos um perfil: astronauta ou médico")
        if self.password != self.password_confirmation:
            raise ValueError("Password confirmation does not match")

        return self


class UserResponse(SQLModel):
    is_astronaut: bool = False
    is_physician: bool = False
    id: int
    name: str
    email: str
    phone: str | None = None
    address: str | None = None

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