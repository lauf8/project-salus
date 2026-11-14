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
    is_psychologist: bool = False
    is_nutritionist: bool = False
    is_nurse: bool = False
    is_observer: bool = False
    is_mission_admin: bool = False
    is_global_admin: bool = False
    is_active: bool = True
    allergy_screening_completed: bool = False
    hashed_password:str