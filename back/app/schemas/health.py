from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, PrivateAttr, model_validator

from app.data.symptoms import SYMPTOM_LABELS
from app.schemas.preflight import InputModel, OutputModel


Indicator = Literal['heart_rate', 'blood_pressure', 'respiratory_rate', 'oxygen_saturation', 'body_temperature', 'consciousness', 'sleep_duration', 'sleep_quality', 'fatigue', 'mood', 'attention', 'blood_glucose']
Source = Literal['self_report', 'manual_measurement', 'device']
Symptom = Literal[tuple(SYMPTOM_LABELS)]
UNITS = {
    'heart_rate': 'bpm', 'blood_pressure': 'mmHg', 'respiratory_rate': 'respirações/min',
    'blood_glucose': 'mg/dL', 'oxygen_saturation': '%', 'body_temperature': '°C', 'consciousness': 'AVPU',
    'sleep_duration': 'min', 'sleep_quality': '1–5', 'fatigue': '0–10', 'mood': '1–5', 'attention': None,
}


class ObservationCreate(InputModel):
    mission_id: int | None = Field(default=None, gt=0)
    indicator: Indicator
    collected_at: AwareDatetime
    source: Source
    value: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    systolic: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    diastolic: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    category: str | None = None
    note: str | None = Field(default=None, max_length=4000)
    sleep_started_at: AwareDatetime | None = None
    sleep_ended_at: AwareDatetime | None = None
    is_preflight_reference: bool = False

    unit: str | None = None
    activity: Literal['rest', 'exercise', 'unknown'] = 'unknown'
    supplemental_oxygen: bool | None = None
    signal_quality: Literal['good', 'poor', 'unknown'] = 'unknown'
    glucose_context: Literal['fasting', 'after_meal', 'unknown'] = 'unknown'
    symptoms_status: Literal['present', 'absent', 'unknown'] = 'unknown'
    symptoms: list[Symptom] = Field(default_factory=list)
    acute_confusion: bool | None = None
    client_request_id: UUID | None = None
    _original_values: dict = PrivateAttr(default_factory=dict)

    @model_validator(mode='after')
    def validate_observation(self):
        self._original_values = {'value': self.value, 'systolic': self.systolic, 'diastolic': self.diastolic, 'unit': self.unit or UNITS[self.indicator]}
        canonical = UNITS[self.indicator]
        unit = self.unit or canonical
        if self.indicator == 'body_temperature' and unit == '°F':
            if self.value is not None:
                self.value = round((self.value - 32) * 5 / 9, 6)
        elif self.indicator == 'blood_glucose' and unit == 'mmol/L':
            if self.value is not None:
                self.value = round(self.value * 18.0182, 6)
        elif self.indicator == 'blood_pressure' and unit == 'kPa':
            self.systolic = round(self.systolic * 7.50061683, 6) if self.systolic is not None else None
            self.diastolic = round(self.diastolic * 7.50061683, 6) if self.diastolic is not None else None
        elif self.indicator == 'oxygen_saturation' and unit == 'fraction':
            if self.value is not None:
                self.value = round(self.value * 100, 6)
        elif self.indicator == 'sleep_duration' and unit == 'h':
            if self.value is not None:
                self.value = round(self.value * 60, 6)
        elif unit != canonical:
            raise ValueError('Unidade não suportada para este indicador')
        self.unit = canonical
        if self.value is not None and self.value < 0:
            raise ValueError('O valor normalizado não pode ser negativo')
        if len(self.symptoms) != len(set(self.symptoms)):
            raise ValueError('Não repita os sintomas')
        self.symptoms = sorted(self.symptoms)
        if self.symptoms:
            if self.symptoms_status == 'absent':
                raise ValueError('Sintomas presentes não podem ser marcados como ausentes')
            self.symptoms_status = 'present'
        elif self.symptoms_status == 'present':
            raise ValueError('Selecione os sintomas presentes')
        if self.acute_confusion is not None and self.indicator not in ('attention', 'consciousness'):
            raise ValueError('Confusão aguda deve ser registrada em atenção ou consciência')
        for name in ('collected_at', 'sleep_started_at', 'sleep_ended_at'):
            timestamp = getattr(self, name)
            if timestamp is not None:
                setattr(self, name, timestamp.astimezone(timezone.utc))
        if self.collected_at > datetime.now(timezone.utc):
            raise ValueError('O horário da coleta não pode estar no futuro')
        if self.source == 'device':
            raise ValueError('Não existe integração de dispositivo configurada')
        if self.indicator == 'consciousness' and self.source != 'manual_measurement':
            raise ValueError('AVPU exige avaliação manual por outra pessoa autorizada')
        if self.is_preflight_reference and self.mission_id is None:
            raise ValueError('A referência pré-missão exige uma missão')
        if self.sleep_started_at or self.sleep_ended_at:
            if self.indicator != 'sleep_duration' or not (self.sleep_started_at and self.sleep_ended_at):
                raise ValueError('Informe início e fim somente para uma sessão de sono')
            if self.sleep_ended_at <= self.sleep_started_at or self.sleep_ended_at > self.collected_at:
                raise ValueError('O fim do sono deve ser posterior ao início e não pode exceder a coleta')
            duration = int((self.sleep_ended_at - self.sleep_started_at).total_seconds() // 60)
            if duration < 1:
                raise ValueError('A sessão deve durar pelo menos um minuto')
            if self.value is not None and self.value != duration:
                raise ValueError('A duração informada difere da sessão de sono')
            self.value = duration
        if self.indicator == 'blood_pressure':
            if self.systolic is None or self.diastolic is None or self.systolic <= self.diastolic:
                raise ValueError('Informe sistólica e diastólica juntas, com sistólica maior que diastólica')
            if self.value is not None or self.category is not None:
                raise ValueError('Pressão arterial aceita apenas sistólica e diastólica')
        elif self.indicator in ('consciousness', 'attention'):
            options = ('alert', 'voice', 'pain', 'unresponsive') if self.indicator == 'consciousness' else ('better', 'usual', 'worse')
            if self.category not in options or any(v is not None for v in (self.value, self.systolic, self.diastolic)):
                raise ValueError('Selecione uma categoria válida para o indicador')
        else:
            if self.value is None or any(v is not None for v in (self.category, self.systolic, self.diastolic)):
                raise ValueError('Informe um valor numérico para o indicador')
            if self.indicator in ('heart_rate', 'respiratory_rate', 'body_temperature', 'blood_glucose') and self.value <= 0:
                raise ValueError('O valor deve ser maior que zero')
            if self.indicator == 'oxygen_saturation' and self.value > 100:
                raise ValueError('A saturação deve estar entre 0 e 100%')
            if self.indicator in ('sleep_quality', 'mood', 'fatigue', 'sleep_duration') and not float(self.value).is_integer():
                raise ValueError('Este indicador exige um número inteiro')
            if self.indicator in ('sleep_quality', 'mood') and not 1 <= self.value <= 5:
                raise ValueError('A escala vai de 1 a 5')
            if self.indicator == 'fatigue' and not 0 <= self.value <= 10:
                raise ValueError('A escala de fadiga vai de 0 a 10')
        return self


class ObservationResponse(OutputModel):
    id: int
    astronaut_id: int
    mission_id: int | None
    indicator: Indicator
    collected_at: datetime
    recorded_at: datetime
    source: Source
    recorded_by_user_id: int
    value: float | None
    systolic: float | None
    diastolic: float | None
    category: str | None
    note: str | None
    sleep_started_at: datetime | None
    sleep_ended_at: datetime | None
    is_preflight_reference: bool
    unit: str | None = None
    original_values: dict | None = None
    activity: str = 'unknown'
    supplemental_oxygen: bool | None = None
    signal_quality: str = 'unknown'
    glucose_context: str = 'unknown'
    symptoms_status: str = 'unknown'
    symptoms: list[str] = Field(default_factory=list)
    acute_confusion: bool | None = None
    client_request_id: str | None = None
    evaluation_status: str = 'not_evaluated'
    evaluation_notes: list[str] = Field(default_factory=list)
    evaluation_profile: dict | None = None


class IndicatorSummary(OutputModel):
    indicator: Indicator
    unit: str | None
    latest: ObservationResponse | None
    previous: ObservationResponse | None
    preflight_reference: ObservationResponse | None
    previous_delta: dict[str, float] | None
    reference_delta: dict[str, float] | None
    trend: Literal['increasing', 'decreasing', 'stable', 'mixed'] | None
    sequence: list[ObservationResponse]
    measurement_status: Literal['no_measurement', 'stale', 'insufficient_quality', 'evaluated', 'not_evaluated'] = 'not_evaluated'
    evaluation_notes: list[str] = Field(default_factory=list)


class HealthSummary(OutputModel):
    astronaut_id: int
    mission_id: int | None
    can_record: bool
    can_record_consciousness: bool
    can_set_reference: bool
    indicators: list[IndicatorSummary]
