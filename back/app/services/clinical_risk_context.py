CONTEXTS = {
    'low_blood_glucose': {
        'title': 'Low blood glucose / hypoglycemia signal',
        'condition': 'hypoglycemia_signal',
        'source_title': 'NIDDK — Low Blood Glucose (Hypoglycemia)',
        'source_url': 'https://www.niddk.nih.gov/health-information/diabetes/overview/preventing-problems/low-blood-glucose-hypoglycemia',
    },
    'low_oxygen_saturation': {
        'title': 'Low oxygen / respiratory risk signal',
        'condition': 'respiratory_signal',
        'source_title': 'NHLBI — Respiratory Failure: Symptoms',
        'source_url': 'https://www.nhlbi.nih.gov/health/respiratory-failure/symptoms',
    },
}


def clinical_context(alert):
    context = CONTEXTS.get(alert.rule_id)
    observation = alert.latest_observation or alert.trigger_observation
    if context is None and alert.indicator == 'body_temperature' and observation.value is not None and observation.value > 38:
        context = {
            'title': 'Fever / possible infection signal',
            'condition': 'fever_signal',
            'source_title': 'MedlinePlus — Fever',
            'source_url': 'https://medlineplus.gov/fever.html',
        }
    return {
        **(context or {'title': 'Health change requiring medical review', 'condition': 'clinical_change', 'source_title': None, 'source_url': None}),
        'assessment_type': 'screening_signal', 'diagnosis_confirmed': False, 'disease_probability': None,
        'medical_review_required': True,
        'next_step': 'Have the assigned flight surgeon review the measurement and symptoms. Use the existing clinical alert workflow.',
    }
