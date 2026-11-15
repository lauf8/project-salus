from sqlmodel import select

from app.models.predictive import PredictionModel
from app.services.predictive.config import rules_config
from app.services.predictive.data_collection import AstronautDataCollector, fingerprint
from app.services.predictive.features import aware, build_features, rounded
from app.services.predictive.rules import evaluate_anomalies, evaluate_plan_targets, evaluate_rules, insufficient_predictions
from app.services.predictive.training import OUTCOMES, infer, probability_level


DOMAIN_FOR_OUTCOME = {'elevated_fatigue_24h': 'sleep'}


class HealthRiskPredictionService:
    def __init__(self, session, config=None):
        self.session = session
        self.config = config or rules_config()

    def active_models(self):
        return self.session.exec(select(PredictionModel).where(PredictionModel.subject_type == 'astronaut', PredictionModel.kind == 'supervised', PredictionModel.status == 'active')).all()

    def collect(self, astronaut_id, mission_id, as_of):
        records, context = AstronautDataCollector(self.session).collect(astronaut_id, mission_id, as_of)
        return records, context, fingerprint(records, context)

    def predict(self, records, context, as_of):
        as_of = aware(as_of)
        features, quality = build_features(records, as_of, self.config)
        predictions, domain_state = evaluate_rules(features, quality, context, self.config)
        predictions.extend(evaluate_anomalies(features, quality, self.config))
        predictions.extend(evaluate_plan_targets(context, self.config))
        predictions.extend(self.model_predictions(features))
        predictions.extend(insufficient_predictions(domain_state, self.config))
        self.attach_clinical_context(predictions, context)
        return features, quality, predictions

    def model_predictions(self, features):
        results = []
        for model in self.active_models():
            outcome = OUTCOMES.get(model.predicted_outcome)
            metrics = model.validation_metrics or {}
            if outcome is None or not metrics.get('passed'):
                continue
            try:
                probability, missing = infer(model, features)
            except Exception as exc:
                results.append(self.model_failure(model, outcome, str(exc)[:300]))
                continue
            if probability is None:
                results.append(self.model_failure(model, outcome, f'Required features missing ({rounded(missing * 100, 1)}% of model inputs)'))
                continue
            prevalence = metrics.get('data', {}).get('train_positives', 0) / max(1, metrics.get('data', {}).get('train_samples', 1))
            selected = metrics.get('metrics', {})
            results.append({
                'domain': DOMAIN_FOR_OUTCOME.get(outcome.name, 'other'), 'risk_type': outcome.name, 'title': outcome.description,
                'prediction_kind': 'ml', 'model_id': model.id, 'score': rounded(probability, 4),
                'score_meaning': 'Calibrated probability from a validated model for the defined outcome and horizon.',
                'calibrated_probability': rounded(probability, 4), 'risk_level': probability_level(probability, prevalence),
                'horizon_hours': outcome.horizon_hours,
                'factors': [{'feature': name, 'value': features.get(name.rsplit('.', 1)[0], {}).get(name.rsplit('.', 1)[1])} for name in metrics.get('feature_names', [])[:10]],
                'data_quality': {'missing_feature_ratio': rounded(missing, 3)},
                'uncertainty': {'level': 'moderate', 'calibration_error': selected.get('expected_calibration_error'), 'brier': selected.get('brier'),
                                'note': 'Validated on historical data from this system only. Synthetic data is never used as clinical validation.'},
                'evidence': {'model_name': model.name, 'model_version': model.version, 'validation': {key: selected.get(key) for key in ('precision', 'recall', 'f1', 'pr_auc', 'brier')}},
            })
        return results

    def model_failure(self, model, outcome, reason):
        return {
            'domain': DOMAIN_FOR_OUTCOME.get(outcome.name, 'other'), 'risk_type': f'{outcome.name}_insufficient_data', 'title': outcome.description,
            'prediction_kind': 'insufficient_data', 'model_id': model.id, 'score': None, 'score_meaning': None, 'calibrated_probability': None,
            'risk_level': 'undetermined', 'horizon_hours': outcome.horizon_hours, 'factors': [],
            'data_quality': {'reason': reason}, 'uncertainty': {'level': 'not_assessable'},
            'evidence': {'model_name': model.name, 'model_version': model.version},
        }

    def attach_clinical_context(self, predictions, context):
        alerts = context.get('active_clinical_alerts') or []
        for prediction in predictions:
            indicators = {item.get('indicator') for item in prediction['factors']}
            related = [alert for alert in alerts if alert['indicator'] in indicators or alert['indicator'] == 'heart_rate' and 'resting_heart_rate' in indicators or alert['indicator'] == 'blood_pressure' and indicators & {'systolic_pressure', 'diastolic_pressure'}]
            if related:
                prediction['evidence']['active_clinical_alerts'] = related
                prediction['evidence']['clinical_alert_precedence'] = 'Active clinical alerts follow the clinical protocol. This prediction never lowers or replaces them.'
