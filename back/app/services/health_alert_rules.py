from copy import deepcopy
from datetime import timedelta, timezone
from functools import lru_cache
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from app.data.symptoms import SYMPTOM_LABELS
from app.schemas.health import UNITS


SEVERITY_RANK = {'attention': 1, 'urgent': 2, 'critical': 3}
INDICATOR_NAMES = {
    'heart_rate': 'Heart rate', 'respiratory_rate': 'Respiratory rate',
    'oxygen_saturation': 'Oxygen saturation', 'body_temperature': 'Body temperature',
    'blood_pressure': 'Blood pressure', 'blood_glucose': 'Blood glucose',
    'sleep_duration': 'Sleep duration', 'sleep_quality': 'Sleep quality',
    'mood': 'Mood', 'fatigue': 'Fatigue', 'attention': 'Changes in attention', 'consciousness': 'Level of consciousness',
}


@lru_cache
def profiles():
    return json.loads((Path(__file__).resolve().parents[1] / 'config' / 'health_alert_profiles.json').read_text(encoding='utf-8'))


def profile_for(settings=None):
    catalog = profiles()
    profile_id = settings.profile_id if settings else catalog['default_profile']
    profile = deepcopy(catalog['profiles'][profile_id])
    profile['rule_version'] = profile['version']
    profile['emergency_channel'] = None
    if settings:
        profile['rule_version'] += f':mission-{settings.mission_id}:r{settings.revision}'
        profile['timezone'] = settings.timezone
        profile['emergency_channel'] = settings.emergency_channel
        if settings.oxygen_thresholds is not None:
            profile['oxygen_thresholds'] = settings.oxygen_thresholds
        profile['high_glucose_thresholds'] = settings.high_glucose_thresholds
        profile['approved_by_user_id'] = settings.approved_by_user_id
        profile['approval_note'] = settings.approval_note
    return profile


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def matches(value, band):
    if value is None:
        return False
    return all({'gt': lambda: value > limit, 'gte': lambda: value >= limit, 'lt': lambda: value < limit, 'lte': lambda: value <= limit}[key]() for key, limit in band.items() if key in ('gt', 'gte', 'lt', 'lte'))


def band_reason(band):
    symbols = {'gt': '>', 'gte': '≥', 'lt': '<', 'lte': '≤'}
    return ' and '.join(f'{symbols[key]} {limit:g}' for key, limit in band.items() if key in symbols)


def display_reading(observation):
    name = INDICATOR_NAMES[observation.indicator]
    if observation.indicator == 'blood_pressure':
        return f'{name} of {observation.systolic:g}/{observation.diastolic:g} mmHg.'
    if observation.value is not None:
        return f'{name} of {observation.value:g} {observation.unit or UNITS[observation.indicator] or "points"}.'
    category = {'alert': 'alert', 'voice': 'responds only to voice', 'pain': 'responds only to pain', 'unresponsive': 'unresponsive', 'better': 'better than usual', 'usual': 'usual', 'worse': 'worse than usual'}.get(observation.category, observation.category)
    return f'{name}: {category}.'


def finding(rule_id, severity, observation, reason, verification=False, sources=None):
    notes = []
    if observation.signal_quality == 'poor':
        notes.append('Insufficient quality; verify the measurement immediately. The initial alert does not wait for confirmation.')
        verification = True
    if observation.supplemental_oxygen is True:
        notes.append('Measurement taken on supplemental oxygen.')
    if observation.activity == 'exercise':
        notes.append('Measurement taken during exercise.')
    if observation.activity == 'unknown' and observation.indicator in ('heart_rate', 'respiratory_rate'):
        notes.append('Unknown activity; confirm the resting context.')
    if severity in ('urgent', 'critical'):
        verification = True
    return {'rule_id': rule_id, 'severity': severity, 'reason': ' '.join([display_reading(observation), reason, *notes]), 'verification_required': verification, 'sources': sources or [observation], 'trigger_observation': observation}


def evaluate_reading(observation, profile):
    results = []
    indicator = observation.indicator
    for rule in profile['rules']:
        if rule['indicator'] != indicator:
            continue
        value = getattr(observation, rule.get('field', 'value'))
        bands = [band for band in rule['bands'] if matches(value, band)]
        if not bands:
            continue
        band = max(bands, key=lambda item: SEVERITY_RANK[item['severity']])
        if rule.get('rest_only') and observation.activity != 'rest':
            extreme = band['severity'] == 'critical'
            if extreme and (observation.activity == 'unknown' or observation.signal_quality == 'poor'):
                results.append(finding(rule['id'] + '_verification', 'urgent', observation, 'Extreme reading without a confirmed resting context. Verify the measurement immediately.', True))
            continue
        results.append(finding(rule['id'], band['severity'], observation, f'Range {band_reason(band)} configured for this profile.'))
    if indicator == 'oxygen_saturation':
        targets = profile['oxygen_thresholds']
        value = observation.value
        if value < targets['normal_min']:
            severity = 'critical' if value < targets['urgent_min'] else 'urgent' if value < targets['attention_min'] else 'attention'
            threshold = targets['urgent_min'] if severity == 'critical' else targets['attention_min'] if severity == 'urgent' else targets['normal_min']
            results.append(finding('low_oxygen_saturation', severity, observation, f'Below the {threshold:g}% limit configured for this profile.'))
    if indicator == 'blood_pressure':
        rule = profile['high_pressure']
        if observation.systolic > rule['systolic_gt'] or observation.diastolic > rule['diastolic_gt']:
            symptoms = set(observation.symptoms) & set(rule['symptoms'])
            severity = 'critical' if observation.symptoms_status == 'present' and symptoms else 'urgent'
            context = 'Recorded symptoms: ' + ', '.join(SYMPTOM_LABELS[key] for key in sorted(symptoms)) + '.' if symptoms else 'Symptoms unknown; record the symptoms and a new measurement.' if observation.symptoms_status == 'unknown' else 'Warning symptoms reported as absent; record a new measurement.'
            results.append(finding('very_high_blood_pressure', severity, observation, f"Systolic > {rule['systolic_gt']} or diastolic > {rule['diastolic_gt']} mmHg configured for this profile. {context}"))
    if indicator == 'blood_glucose':
        thresholds = profile['high_glucose_thresholds'].get(observation.glucose_context, {})
        triggered = [severity for severity, threshold in thresholds.items() if threshold is not None and observation.value >= threshold]
        if triggered:
            severity = max(triggered, key=SEVERITY_RANK.get)
            context = {'fasting': 'while fasting', 'after_meal': 'after a meal', 'unknown': 'without meal context'}[observation.glucose_context]
            source = 'by the medical team' if profile.get('approved_by_user_id') else 'in the simulation profile'
            results.append(finding('high_blood_glucose_' + observation.glucose_context, severity, observation, f'Value {context} ≥ {thresholds[severity]:g} mg/dL configured {source}.'))
    if indicator in ('consciousness', 'attention'):
        if observation.acute_confusion is True or (indicator == 'consciousness' and observation.category in profile['consciousness']['critical_categories']):
            reason = 'Recent-onset confusion recorded.' if observation.acute_confusion is True else 'Response to voice, response to pain or no response recorded.'
            results.append(finding('acute_consciousness', profile['consciousness']['acute_confusion_severity'], observation, reason))
    return results


def evaluate_trend(observation, rows, profile):
    if observation.signal_quality == 'poor':
        return []
    results = []
    zone = ZoneInfo(profile['timezone'])
    for rule in profile['trends']:
        if rule['indicator'] != observation.indicator:
            continue
        daily = {}
        for row in sorted(rows, key=lambda item: (aware(item.collected_at), aware(item.recorded_at), item.id)):
            if row.signal_quality == 'poor':
                continue
            anchor = row.sleep_ended_at if rule.get('night') and row.sleep_ended_at else row.collected_at
            day = aware(anchor).astimezone(zone).date()
            daily[day] = row
        if not daily:
            continue
        last = max(daily)
        sequence = [daily.get(last - timedelta(days=offset)) for offset in range(rule['days'])]
        if observation.id not in {row.id for row in sequence if row is not None}:
            continue
        if all(row is not None and (row.category in rule['categories'] if 'categories' in rule else matches(row.value, rule)) for row in sequence):
            latest = sequence[0]
            period = 'nights' if rule.get('night') else 'days'
            criteria = 'change from usual' if 'categories' in rule else band_reason(rule) + (' minutes' if observation.indicator == 'sleep_duration' else ' points')
            results.append(finding(rule['id'], 'attention', latest, f'{criteria} on {rule["days"]} consecutive {period} in time zone {profile["timezone"]}. One valid record per {"night" if rule.get("night") else "day"}.', sources=list(reversed(sequence))))
    return results
