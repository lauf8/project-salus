from datetime import date, timezone
import math

from fastapi import HTTPException


def snapshot(definition):
    return {key: getattr(definition, key) for key in ('id', 'exam_type_id', 'code', 'name', 'revision', 'description', 'specimen', 'preparation', 'applicability_notes', 'source_url', 'source_section', 'source_page', 'fields')}


def validate_result(snapshot_value, values, ranges, collected_at, performed_at):
    fields = {field['code']: field for field in (snapshot_value or {}).get('fields', [])}
    if set(values) - set(fields) or set(ranges) - set(fields):
        raise HTTPException(422, 'The result contains fields that do not belong to this exam')
    for code, field in fields.items():
        value = values.get(code)
        missing = value is None or (isinstance(value, str) and not value.strip())
        if missing:
            if field.get('required'):
                raise HTTPException(422, f'Fill in the required field: {field["label"]}')
            continue
        kind = field['type']
        valid = False
        if kind == 'number':
            valid = type(value) in (int, float) and math.isfinite(value)
        elif kind == 'boolean':
            valid = type(value) is bool
        elif kind in ('text', 'textarea'):
            valid = isinstance(value, str) and len(value) <= (10000 if kind == 'textarea' else 1000)
        elif kind == 'select':
            valid = isinstance(value, str) and value in {option['value'] for option in field['options']}
        elif kind == 'date' and isinstance(value, str):
            try:
                valid = date.fromisoformat(value).isoformat() == value
            except ValueError:
                pass
        if not valid:
            raise HTTPException(422, f'Invalid value for field: {field["label"]}')
    for code, value in ranges.items():
        if fields[code]['type'] != 'number' or not isinstance(value, str) or len(value) > 300:
            raise HTTPException(422, 'Provide laboratory references only for numeric fields')
    if collected_at:
        aware = lambda stamp: stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
        if aware(collected_at) > aware(performed_at):
            raise HTTPException(422, 'Collection cannot happen after the exam was performed')
