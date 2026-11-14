from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from app.schemas.preflight import InputModel, OutputModel


class ExamFieldOption(InputModel):
    value: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    label: str = Field(min_length=1, max_length=160)


class ExamField(InputModel):
    code: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    label: str = Field(min_length=1, max_length=160)
    type: Literal['number', 'text', 'textarea', 'select', 'boolean', 'date']
    unit: str | None = Field(default=None, max_length=40)
    required: bool = False
    options: list[ExamFieldOption] = Field(default_factory=list, max_length=40)

    @model_validator(mode='after')
    def validate_options(self):
        if self.type == 'select' and not self.options:
            raise ValueError('Um campo de seleção exige opções')
        if self.type != 'select' and self.options:
            raise ValueError('Opções são permitidas apenas em campos de seleção')
        if self.unit and self.type != 'number':
            raise ValueError('Unidades são permitidas apenas em campos numéricos')
        if len({option.value for option in self.options}) != len(self.options):
            raise ValueError('As opções não podem ter valores duplicados')
        return self


class ExamCreate(InputModel):
    exam_type_id: int = Field(gt=0)
    code: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    specimen: str | None = Field(default=None, max_length=200)
    preparation: str | None = Field(default=None, max_length=2000)
    applicability_notes: str | None = Field(default=None, max_length=4000)
    source_url: HttpUrl | None = None
    source_section: str | None = Field(default=None, max_length=300)
    source_page: int | None = Field(default=None, ge=1, le=10000)
    fields: list[ExamField] = Field(min_length=1, max_length=100)
    is_active: bool = True

    @model_validator(mode='after')
    def validate_fields(self):
        if len({field.code for field in self.fields}) != len(self.fields):
            raise ValueError('Os campos do exame devem ter identificadores únicos')
        return self


class ExamUpdate(ExamCreate):
    expected_revision: int = Field(ge=1)


class ExamResponse(OutputModel):
    id: int
    exam_type_id: int
    code: str
    name: str
    description: str | None
    specimen: str | None
    preparation: str | None
    applicability_notes: str | None
    source_url: str | None
    source_section: str | None
    source_page: int | None
    fields: list[ExamField]
    revision: int
    is_active: bool
