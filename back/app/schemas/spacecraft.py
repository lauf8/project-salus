from typing import Annotated, Literal

from pydantic import Field, HttpUrl, StrictInt

from app.schemas.preflight import InputModel, OutputModel, PatchInput


PositiveNumber = Annotated[float, Field(gt=0, allow_inf_nan=False)]
ManufacturedYear = Annotated[StrictInt, Field(gt=0, le=32767)]
RequiredText = Annotated[str, Field(min_length=1)]


class Dimensions(InputModel):
    length: PositiveNumber | None = None
    width: PositiveNumber | None = None
    height: PositiveNumber | None = None
    diameter: PositiveNumber | None = None


class Material(InputModel):
    component: RequiredText
    material: RequiredText
    location: str | None = None
    specification: str | None = None
    contact_environment: str | None = None


class TechnicalSpecifications(InputModel):
    dimensions_m: Dimensions | None = None
    dry_mass_kg: PositiveNumber | None = None
    materials: list[Material] | None = None
    thermal_insulation: str | None = None
    shielding: str | None = None


class SpacecraftFields(InputModel):
    maximum_crew_capacity: Annotated[StrictInt, Field(gt=0, le=2147483647)] | None = None
    model: str | None = None
    manufacturer: str | None = None
    serial_number: str | None = None
    manufactured_year: ManufacturedYear | None = None
    description: str | None = None
    technical_reference_url: HttpUrl | None = None


class SpacecraftCreate(SpacecraftFields):
    name: RequiredText


class SpacecraftPatch(SpacecraftFields, PatchInput):
    non_null_fields = {'name'}
    name: RequiredText | None = None


class SpacecraftResponse(SpacecraftCreate, OutputModel):
    status: Literal["available", "in_use"]
    id: int


class ModuleFields(InputModel):
    purpose: str | None = None
    manufacturer: str | None = None
    serial_number: str | None = None
    manufactured_year: ManufacturedYear | None = None
    is_pressurized: bool | None = None
    is_habitable: bool | None = None
    pressurized_volume_m3: PositiveNumber | None = None
    technical_specifications: TechnicalSpecifications | None = Field(default=None, description='When supplied in PATCH, replaces the complete technical specification. Omitted fields in the specification are not merged. Use null to clear it.')
    technical_reference_url: HttpUrl | None = None


class ModuleCreate(ModuleFields):
    code: RequiredText
    name: RequiredText


class ModulePatch(ModuleFields, PatchInput):
    non_null_fields = {'code', 'name'}
    code: RequiredText | None = None
    name: RequiredText | None = None


class ModuleResponse(ModuleCreate, OutputModel):
    id: int
    spacecraft_id: int
