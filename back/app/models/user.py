from sqlmodel import Field, SQLModel

class User(SQLModel, table=True):
    __tablename__ = "users"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str = Field(index=True, unique=True)
    phone: str | None = None
    address: str | None = None
    is_astronaut: bool = False
    is_physician: bool = False
    allergy_screening_completed: bool = False
    hashed_password:str