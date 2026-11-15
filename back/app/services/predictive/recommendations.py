from collections import defaultdict

from sqlmodel import select

from app.models.predictive import RecommendationAction, RecommendationEvent, RecommendationOutcome
from app.services.predictive.config import recommendation_catalog


LEVEL_RANK = {'undetermined': -1, 'none': 0, 'low': 1, 'moderate': 2, 'high': 3}
EVIDENCE_QUALITY = {'documented_standard': 1.0, 'documented_research': 0.8, 'historical_records': 0.6, 'expert_opinion': 0.4}
URGENCY = {'high': 'within_24_hours', 'moderate': 'within_72_hours', 'low': 'routine'}
WEIGHTS = {'urgency': 0.25, 'relevance': 0.2, 'evidence_quality': 0.15, 'context_fit': 0.1, 'feasibility': 0.1, 'historical_outcomes': 0.1, 'catalog_priority': 0.1}


def sync_catalog(session):
    catalog = recommendation_catalog()
    created = 0
    for entry in catalog['actions']:
        existing = session.exec(select(RecommendationAction).where(RecommendationAction.code == entry['code'], RecommendationAction.version == entry['version'])).first()
        if existing is None:
            session.add(RecommendationAction(**entry, approval_status='approved', approved_by=catalog['approved_by']))
            created += 1
        older = session.exec(select(RecommendationAction).where(RecommendationAction.code == entry['code'], RecommendationAction.version < entry['version'], RecommendationAction.approval_status == 'approved')).all()
        for action in older:
            action.approval_status = 'retired'
            session.add(action)
    session.flush()
    return created


def contraindications(action, context):
    reasons = []
    for rule in action.contraindications:
        if rule['type'] == 'active_clinical_alert_severity':
            if any(alert['severity'] in rule['values'] for alert in context.get('active_clinical_alerts') or []):
                reasons.append(rule['reason'])
        elif rule['type'] == 'pending_psychology_request':
            if context.get('pending_psychology_request'):
                reasons.append(rule['reason'])
        else:
            reasons.append(f"Unknown contraindication type {rule['type']}; the action is excluded until the catalog is reviewed.")
    return reasons


def eligibility(action, prediction, context):
    reasons = []
    rules = action.eligibility or {}
    minimum = rules.get('minimum_risk_level')
    if minimum and LEVEL_RANK.get(prediction['risk_level'], -1) < LEVEL_RANK[minimum]:
        reasons.append(f"Risk level {prediction['risk_level']} is below the eligibility minimum {minimum}")
    statuses = rules.get('mission_statuses')
    if statuses and context.get('mission_status') not in statuses:
        reasons.append(f"Mission status {context.get('mission_status')} is outside {', '.join(statuses)}")
    return reasons


def ranking(action, prediction, context, history):
    outcome = history.get(action.code, {'improved': 0, 'total': 0})
    components = {
        'urgency': max(0, LEVEL_RANK.get(prediction['risk_level'], 0)) / 3,
        'relevance': 1.0 if prediction['risk_type'] in action.risk_types[:1] else 0.85,
        'evidence_quality': EVIDENCE_QUALITY.get(action.evidence_quality, 0.4),
        'context_fit': 1.0 if context.get('mission_status') in (None, 'in_progress') else 0.7,
        'feasibility': max(0.0, min(1.0, action.feasibility)),
        'historical_outcomes': (outcome['improved'] + 1) / (outcome['total'] + 2),
        'catalog_priority': (6 - action.priority) / 5,
    }
    score = sum(WEIGHTS[key] * value for key, value in components.items())
    return round(score, 4), {key: round(value, 4) for key, value in components.items()} | {'outcome_history': outcome, 'weights': WEIGHTS}


class RecommendationEngine:
    def __init__(self, session):
        self.session = session

    def approved_actions(self):
        return self.session.exec(select(RecommendationAction).where(RecommendationAction.approval_status == 'approved')).all()

    def outcome_history(self):
        rows = self.session.exec(select(RecommendationOutcome, RecommendationEvent, RecommendationAction).join(RecommendationEvent, RecommendationEvent.id == RecommendationOutcome.recommendation_id).join(RecommendationAction, RecommendationAction.id == RecommendationEvent.action_id)).all()
        history = defaultdict(lambda: {'improved': 0, 'total': 0})
        for outcome, _, action in rows:
            if outcome.result == 'inconclusive':
                continue
            history[action.code]['total'] += 1
            history[action.code]['improved'] += outcome.result == 'improved'
        return dict(history)

    def recommend(self, prediction, context, actions=None, history=None):
        actions = self.approved_actions() if actions is None else actions
        history = self.outcome_history() if history is None else history
        if prediction['prediction_kind'] == 'insufficient_data':
            return [], []
        selected, excluded = [], []
        for action in actions:
            if prediction['risk_type'] not in action.risk_types:
                continue
            blocked = contraindications(action, context)
            if blocked:
                excluded.append({'action_code': action.code, 'action_id': action.id, 'reason': 'contraindicated', 'details': blocked})
                continue
            ineligible = eligibility(action, prediction, context)
            if ineligible:
                excluded.append({'action_code': action.code, 'action_id': action.id, 'reason': 'not_eligible', 'details': ineligible})
                continue
            score, components = ranking(action, prediction, context, history)
            selected.append({'action': action, 'score': score, 'components': components, 'urgency': URGENCY.get(prediction['risk_level'], 'routine'),
                             'rationale': self.rationale(action, prediction)})
        selected.sort(key=lambda row: (-row['score'], row['action'].priority, row['action'].code))
        return selected, excluded

    def rationale(self, action, prediction):
        factors = ', '.join(sorted({str(item.get('indicator') or item.get('category') or item.get('food_name') or item.get('feature') or 'context') for item in prediction['factors']})) or 'recorded context'
        kind = {'rule': 'rule-based signal', 'anomaly': 'statistical anomaly', 'ml': 'validated model prediction'}[prediction['prediction_kind']]
        return f"{action.name}: suggested for a {kind} ({prediction['title']}; level {prediction['risk_level']}) based on {factors}. This is a preventive suggestion for human review, not a diagnosis or prescription."
