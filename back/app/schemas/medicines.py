from pydantic import Field, model_validator

from app.schemas.preflight import InputModel, OutputModel, PatchInput


class NameInput(InputModel):
    name: str = Field(min_length=1, max_length=200)


class IngredientIds(InputModel):
    active_ingredient_ids: list[int] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_ids(self):
        ids = self.active_ingredient_ids
        if any(value <= 0 for value in ids) or len(ids) != len(set(ids)):
            raise ValueError('Informe IDs positivos de princípios ativos sem duplicações')
        return self


class MedicineCreate(NameInput, IngredientIds):
    main_indications: str | None = Field(default=None, max_length=4000)


class MedicinePatch(PatchInput):
    non_null_fields = {'name', 'active_ingredient_ids'}
    name: str | None = Field(default=None, min_length=1, max_length=200)
    active_ingredient_ids: list[int] | None = None
    main_indications: str | None = Field(default=None, max_length=4000)

    @model_validator(mode='after')
    def validate_ids(self):
        if self.active_ingredient_ids is not None:
            IngredientIds(active_ingredient_ids=self.active_ingredient_ids)
        return self


class NamedResponse(OutputModel):
    id: int
    name: str


class MedicineResponse(NamedResponse):
    main_indications: str | None = None
    active_ingredients: list[NamedResponse]


class AllergyUpdate(IngredientIds):
    allergy_screening_completed: bool


class AllergyResponse(OutputModel):
    crew_member_id: int
    allergy_screening_completed: bool
    active_ingredients: list[NamedResponse]
    can_edit: bool
