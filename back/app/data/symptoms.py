"""Catálogo de sintomas aceitos nas medições e no acompanhamento pós-evento.

Os sintomas de radiação são os efeitos prodrômicos descritos no NASA SP-2009-3405,
cap. 5 (náusea, vômito, perda de apetite e fadiga nas primeiras 48 h) e a reação
de pele, mais provável quando o tripulante estava em EVA durante o SEP.
"""

WARNING_SYMPTOMS = {
    'chest_pain': 'dor no peito',
    'shortness_of_breath': 'falta de ar',
    'sudden_weakness': 'fraqueza súbita',
    'visual_changes': 'alteração visual',
    'speech_difficulty': 'dificuldade para falar',
}

RADIATION_SYMPTOMS = {
    'nausea': 'náusea',
    'vomiting': 'vômito',
    'anorexia': 'perda de apetite',
    'fatigue': 'fadiga',
    'skin_erythema': 'vermelhidão ou ardor na pele',
}

SYMPTOM_LABELS = {**WARNING_SYMPTOMS, **RADIATION_SYMPTOMS}
