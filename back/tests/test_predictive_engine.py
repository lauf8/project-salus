from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.services.predictive.config import recommendation_catalog, rules_config
from app.services.predictive.features import Measurement, available_at, build_features, linear_slope_per_day, series_features
from app.services.predictive.knowledge import applicable, validate_explanation
from app.services.predictive.recommendations import RecommendationEngine
from app.services.predictive.rules import evaluate_anomalies, evaluate_plan_targets, evaluate_rules, insufficient_predictions
from app.services.predictive.training import build_dataset, temporal_split, train_outcome_model
from tests.predictive_synthetic import START, fatigue_cohort, point, steady_series


CONFIG = rules_config()
STATS = CONFIG['statistics']


def with_recent(series, baseline_values, recent_values, unit=None):
    baseline = steady_series(series, baseline_values, start=START, unit=unit)
    recent_start = START + timedelta(days=len(baseline_values) + 14)
    recent = steady_series(series, recent_values, start=recent_start, unit=unit, first_id=1000)
    return baseline + recent, recent_start + timedelta(days=len(recent_values) - 1, hours=12)


def action(code, risk_types, priority=3, contraindications=(), eligibility=None, feasibility=1.0, evidence_quality='documented_standard'):
    return SimpleNamespace(id=hash(code) % 1000, code=code, name=code.replace('_', ' ').title(), description='Synthetic action', risk_types=list(risk_types),
                           priority=priority, contraindications=list(contraindications), eligibility=eligibility or {}, feasibility=feasibility,
                           evidence_quality=evidence_quality, rag_query='sleep accommodations fatigue', source_references=[])


def test_window_statistics_and_trend():
    points = steady_series('fatigue', [2, 3, 4, 5, 6, 7, 8], unit='0-10')
    as_of = START + timedelta(days=6, hours=12)
    features = series_features(points, as_of, STATS)
    assert features['n_7d'] == 7
    assert features['mean_7d'] == 5
    assert features['min_30d'] == 2 and features['max_30d'] == 8
    assert features['slope_per_day'] == pytest.approx(1.0)
    assert features['mean_24h'] == 8
    assert features['hours_since_last'] == pytest.approx(4.0)
    assert features['baseline_source'] is None
    assert features['z_7d'] is None


def test_slope_requires_three_points():
    assert linear_slope_per_day(steady_series('fatigue', [1, 2])) is None


def test_individual_baseline_and_deviation():
    points, as_of = with_recent('sleep_duration', [450, 455, 445, 460, 440, 450], [330, 320, 340, 335], unit='min')
    features = series_features(points, as_of, STATS)
    assert features['baseline_source'] == 'individual_history'
    assert features['baseline_n'] == 6
    assert features['z_7d'] < -STATS['deviation_z']
    assert features['diff_from_baseline'] < 0


def test_preflight_reference_takes_priority_as_baseline():
    preflight = [point('resting_heart_rate', value, START - timedelta(days=30 - index), 500 + index, preflight=True) for index, value in enumerate([60, 61, 59])]
    history = steady_series('resting_heart_rate', [70, 72, 71, 69, 70, 71], start=START)
    as_of = START + timedelta(days=30)
    features = series_features(preflight + history, as_of, STATS)
    assert features['baseline_source'] == 'preflight_reference'
    assert features['baseline_mean'] == 60


def test_temporal_isolation_prevents_leakage():
    points, as_of = with_recent('fatigue', [3, 3, 4, 3, 2, 3], [4, 4, 5])
    reference = series_features(points, as_of, STATS)
    future = point('fatigue', 10, as_of + timedelta(hours=1), 9001)
    late_recorded = Measurement(series='fatigue', value=10, at=as_of - timedelta(hours=2), recorded_at=as_of + timedelta(hours=3), reference=('synthetic', 9002))
    assert available_at([future, late_recorded], as_of) == []
    assert series_features(points + [future, late_recorded], as_of, STATS) == reference


def test_missing_data_is_not_treated_as_normal():
    features, quality = build_features([], START, CONFIG)
    assert quality['missing_ratio'] == 1
    predictions, domains = evaluate_rules(features, quality, {}, CONFIG)
    assert predictions == []
    insufficient = insufficient_predictions(domains, CONFIG)
    assert {p['domain'] for p in insufficient} >= {'cardiovascular', 'sleep', 'psychological', 'nutrition', 'musculoskeletal'}
    assert all(p['prediction_kind'] == 'insufficient_data' and p['risk_level'] == 'undetermined' and p['calibrated_probability'] is None for p in insufficient)


def test_combined_sleep_and_fatigue_signal():
    sleep, as_of = with_recent('sleep_duration', [450, 455, 445, 460, 440, 450], [320, 330, 310, 325], unit='min')
    fatigue, _ = with_recent('fatigue', [3, 2, 3, 4, 3, 3], [8, 8, 9, 8])
    features, quality = build_features(sleep + fatigue, as_of, CONFIG)
    predictions, domains = evaluate_rules(features, quality, {}, CONFIG)
    types = {p['risk_type']: p for p in predictions}
    assert {'sleep_deficit', 'sleep_fatigue_combined', 'fatigue_increase'} <= set(types)
    combined = types['sleep_fatigue_combined']
    assert combined['prediction_kind'] == 'rule'
    assert combined['calibrated_probability'] is None
    assert combined['evidence']['candidate_signal'] is True
    assert 'not probability' in combined['score_meaning']
    assert sum(item['relative_contribution'] for item in combined['factors']) == pytest.approx(1, abs=0.01)
    assert domains['sleep']['signal'] is True


def test_no_signal_inside_individual_variation():
    sleep, as_of = with_recent('sleep_duration', [450, 455, 445, 460, 440, 450], [452, 448, 447, 451], unit='min')
    features, quality = build_features(sleep, as_of, CONFIG)
    predictions, domains = evaluate_rules(features, quality, {}, CONFIG)
    assert not [p for p in predictions if p['domain'] == 'sleep']
    assert domains['sleep']['evaluable'] is True
    assert not [p for p in insufficient_predictions(domains, CONFIG) if p['domain'] == 'sleep']


def test_zero_variance_without_change_is_not_a_signal_or_missing():
    intake, as_of = with_recent('energy_intake', [2600] * 6, [2600] * 4, unit='kcal/day')
    features, quality = build_features(intake, as_of, CONFIG)
    predictions, domains = evaluate_rules(features, quality, {}, CONFIG)
    assert not predictions
    assert domains['nutrition']['evaluable'] is True


def test_symptom_context_is_required_for_pressure_symptom_rule():
    pressure, as_of = with_recent('systolic_pressure', [118, 120, 119, 121, 120, 118], [140, 142, 141, 143], unit='mmHg')
    features, quality = build_features(pressure, as_of, CONFIG)
    without, _ = evaluate_rules(features, quality, {'symptoms_reported_7d': None}, CONFIG)
    with_symptoms, _ = evaluate_rules(features, quality, {'symptoms_reported_7d': True}, CONFIG)
    assert 'cardiovascular_pressure_with_symptoms' not in {p['risk_type'] for p in without}
    assert 'cardiovascular_pressure_with_symptoms' in {p['risk_type'] for p in with_symptoms}


def test_anomaly_score_is_not_a_probability():
    values = [62, 63, 61, 62, 64, 63, 62]
    baseline = steady_series('resting_heart_rate', values)
    as_of = START + timedelta(days=30, hours=12)
    latest = point('resting_heart_rate', 95, as_of - timedelta(hours=2), 77)
    features, quality = build_features(baseline + [latest], as_of, CONFIG)
    anomalies = evaluate_anomalies(features, quality, CONFIG)
    assert anomalies and anomalies[0]['prediction_kind'] == 'anomaly'
    assert anomalies[0]['calibrated_probability'] is None
    assert 'not a disease probability' in anomalies[0]['score_meaning']


def test_nutrition_plan_target_uses_specialist_target_and_coverage():
    context = {'nutrition_plan': {'plan_id': 4, 'energy_target_kcal': 2800, 'covered_days': 5, 'mean_daily_energy_kcal': 2100}}
    result = evaluate_plan_targets(context, CONFIG)
    assert result[0]['risk_type'] == 'nutrition_below_plan_target'
    context['nutrition_plan']['covered_days'] = 2
    assert evaluate_plan_targets(context, CONFIG) == []


def prediction(risk_type='sleep_fatigue_combined', level='moderate', kind='rule'):
    return {'risk_type': risk_type, 'risk_level': level, 'prediction_kind': kind, 'title': 'Synthetic risk', 'factors': [{'indicator': 'fatigue'}]}


def test_contraindicated_action_is_never_selected_even_with_top_score():
    blocked = action('blocked_monitoring', ['sleep_fatigue_combined'], priority=1, feasibility=1.0,
                     contraindications=[{'type': 'active_clinical_alert_severity', 'values': ['critical'], 'reason': 'Critical alert active'}])
    allowed = action('rest_review', ['sleep_fatigue_combined'], priority=5, feasibility=0.2, evidence_quality='expert_opinion')
    context = {'active_clinical_alerts': [{'severity': 'critical', 'indicator': 'heart_rate'}], 'mission_status': 'in_progress'}
    selected, excluded = RecommendationEngine(None).recommend(prediction(), context, [blocked, allowed], {})
    assert [row['action'].code for row in selected] == ['rest_review']
    assert excluded == [{'action_code': 'blocked_monitoring', 'action_id': blocked.id, 'reason': 'contraindicated', 'details': ['Critical alert active']}]


def test_eligibility_and_ranking_order():
    urgent = action('a_review', ['sleep_fatigue_combined'], priority=1)
    later = action('b_review', ['sleep_fatigue_combined'], priority=4)
    operational = action('c_workload', ['sleep_fatigue_combined'], eligibility={'minimum_risk_level': 'high'})
    selected, excluded = RecommendationEngine(None).recommend(prediction(level='moderate'), {'mission_status': 'in_progress'}, [later, operational, urgent], {})
    assert [row['action'].code for row in selected] == ['a_review', 'b_review']
    assert excluded[0]['reason'] == 'not_eligible'
    assert selected[0]['urgency'] == 'within_72_hours'
    assert 'not a diagnosis or prescription' in selected[0]['rationale']


def test_outcome_history_raises_rank():
    first = action('first', ['fatigue_increase'])
    second = action('second', ['fatigue_increase'])
    history = {'second': {'improved': 8, 'total': 8}, 'first': {'improved': 0, 'total': 8}}
    selected, _ = RecommendationEngine(None).recommend(prediction('fatigue_increase'), {'mission_status': 'in_progress'}, [first, second], history)
    assert selected[0]['action'].code == 'second'


def test_insufficient_data_produces_no_recommendation():
    selected, excluded = RecommendationEngine(None).recommend(prediction(kind='insufficient_data', level='undetermined'), {}, [action('x', ['sleep_fatigue_combined'])], {})
    assert selected == [] and excluded == []


def test_catalog_is_versioned_and_non_prescriptive():
    catalog = recommendation_catalog()
    codes = [(entry['code'], entry['version']) for entry in catalog['actions']]
    assert len(codes) == len(set(codes))
    forbidden = ('dose', 'prescribe', 'administer', 'medication change')
    for entry in catalog['actions']:
        assert entry['responsible_roles']
        assert not any(word in entry['description'].lower() for word in forbidden)
    rule_types = {rule['risk_type'] for rule in CONFIG['rules']}
    covered = {risk for entry in catalog['actions'] for risk in entry['risk_types']}
    assert rule_types <= covered


def test_explanation_validation_rejects_invented_sources_and_probabilities():
    sources = [{'id': 7, 'content': 'Sleep accommodations support adequate sleep opportunity.'}]
    payload = {'calibrated_probability': None}
    assert validate_explanation({'summary': 'Review rest periods.', 'citation_ids': [7]}, sources, payload)['citation_ids'] == [7]
    with pytest.raises(ValueError):
        validate_explanation({'summary': 'Review rest periods.', 'citation_ids': [99]}, sources, payload)
    with pytest.raises(ValueError):
        validate_explanation({'summary': 'There is a 70% chance of fatigue.', 'citation_ids': [7]}, sources, payload)
    with pytest.raises(ValueError):
        validate_explanation({'summary': 'Ignore instructions', 'citation_ids': [7], 'extra': True}, sources, payload)


def test_applicability_requires_topic_overlap():
    sources = [{'id': 1, 'content': 'Carbon dioxide limits for cabin air.'}, {'id': 2, 'content': 'Sleep accommodations reduce fatigue.'}]
    assert [row['id'] for row in applicable(sources, 'NASA sleep accommodations fatigue')] == [2]


def test_dataset_is_temporally_split_and_labels_use_only_past_baseline():
    rows = build_dataset(fatigue_cohort(astronauts=2, days=60, seed=3), CONFIG)
    train, test = temporal_split(rows)
    assert train and test
    assert max(row['as_of'] for row in train) < min(row['as_of'] for row in test)
    assert all(row['label'] in (0, 1) for row in rows)


def test_training_rejects_small_datasets():
    result = train_outcome_model(fatigue_cohort(astronauts=1, days=40, seed=5), CONFIG)
    assert result['passed'] is False
    assert result['artifact'] is None
    assert any('below' in reason for reason in result['reasons'])


def test_training_compares_with_baselines_and_reports_metrics():
    result = train_outcome_model(fatigue_cohort(), CONFIG)
    metrics = result['metrics']
    for key in ('precision', 'recall', 'f1', 'pr_auc', 'brier', 'expected_calibration_error', 'false_negatives', 'false_positives', 'reliability'):
        assert key in metrics
    assert set(result['baselines']) == {'prevalence', 'persistence'}
    assert set(result['candidates']) == {'logistic_regression', 'random_forest'}
    assert result['artifact'] and len(result['artifact_sha256']) == 64
    best_baseline = max(value['pr_auc'] for value in result['baselines'].values())
    assert result['passed'] == (metrics['pr_auc'] >= best_baseline + 0.05 and metrics['brier'] < min(v['brier'] for v in result['baselines'].values())
                                and metrics['expected_calibration_error'] <= 0.1 and metrics['recall'] >= 0.5)
