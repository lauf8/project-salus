"""Catalog of symptoms accepted in measurements and in the post-event follow-up.

Radiation symptoms are the prodromal effects described in NASA SP-2009-3405,
chapter 5 (nausea, vomiting, loss of appetite and fatigue in the first 48 h), plus
skin reaction, more likely when the crew member was on EVA during the SEP.
"""

WARNING_SYMPTOMS = {
    'chest_pain': 'chest pain',
    'shortness_of_breath': 'shortness of breath',
    'sudden_weakness': 'sudden weakness',
    'visual_changes': 'visual changes',
    'speech_difficulty': 'difficulty speaking',
}

RADIATION_SYMPTOMS = {
    'nausea': 'nausea',
    'vomiting': 'vomiting',
    'anorexia': 'loss of appetite',
    'fatigue': 'fatigue',
    'skin_erythema': 'skin redness or burning',
}

SYMPTOM_LABELS = {**WARNING_SYMPTOMS, **RADIATION_SYMPTOMS}
