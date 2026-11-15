from app.services.predictive.features import deviation, rounded


Z_MEANING = 'Largest absolute z-score of the 7-day mean against the individual baseline. It measures deviation, not probability.'
ANOMALY_MEANING = 'Robust z-score (median/MAD) of the latest reading against the individual baseline. It is an anomaly score, not a disease probability.'


def factor(indicator, values, z, direction):
    return {
        'indicator': indicator, 'direction': direction, 'z_score': rounded(z, 2),
        'mean_7d': values.get('mean_7d'), 'baseline_mean': values.get('baseline_mean'),
        'baseline_source': values.get('baseline_source'), 'slope_per_day': values.get('slope_per_day'),
        'pct_change_7d': values.get('pct_change_7d'), 'n_7d': values.get('n_7d'), 'baseline_n': values.get('baseline_n'),
        'unit': values.get('unit'),
    }


def with_contributions(factors):
    total = sum(abs(item['z_score'] or 0) for item in factors if item.get('z_score') is not None)
    for item in factors:
        if item.get('z_score') is not None and total:
            item['relative_contribution'] = round(abs(item['z_score']) / total, 3)
    return factors


def uncertainty(factors):
    baseline = min((item['baseline_n'] for item in factors if item.get('baseline_n')), default=0)
    points = min((item['n_7d'] for item in factors if item.get('n_7d')), default=0)
    level = 'high' if baseline < 10 or points < 5 else 'moderate'
    return {'level': level, 'baseline_points': baseline, 'window_points': points,
            'note': 'Rule signals compare recent data with an individual baseline. Small baselines and sparse windows widen uncertainty. Correlated indicators do not establish causation.'}


def rule_level(z_values, combined):
    strongest = max(abs(z) for z in z_values)
    if combined and strongest >= 3:
        return 'high'
    if combined or strongest >= 3:
        return 'moderate'
    return 'low'


def evaluate_condition(condition, features, context, statistics):
    if 'context' in condition:
        return context.get(condition['context']), None
    values = features.get(condition['indicator'])
    if values is None:
        return None, None
    return deviation(values, condition['direction'], statistics['deviation_z'], statistics['minimum_window_points']), values


def evaluate_rules(features, quality, context, config):
    statistics = config['statistics']
    predictions = []
    domain_state = {}
    for rule in config['rules']:
        outcomes = []
        for condition in rule['conditions']:
            result, values = evaluate_condition(condition, features, context, statistics)
            outcomes.append((condition, result, values))
        evaluable = [item for item in outcomes if item[1] is not None]
        met = [item for item in outcomes if item[1] not in (None, False)]
        matched = len(met) == len(outcomes) if rule.get('match', 'all') == 'all' else bool(met)
        state = domain_state.setdefault(rule['domain'], {'evaluable': False, 'signal': False, 'missing': set()})
        for condition, result, _ in outcomes:
            if result is None and 'indicator' in condition:
                state['missing'].add(condition['indicator'])
        if evaluable:
            state['evaluable'] = True
        if not matched:
            continue
        state['signal'] = True
        factors = [factor(condition['indicator'], values, result, condition['direction']) for condition, result, values in met if 'indicator' in condition]
        context_factors = [{'context': condition['context'], 'value': True} for condition, result, _ in met if 'context' in condition]
        z_values = [item['z_score'] for item in factors]
        predictions.append({
            'domain': rule['domain'], 'risk_type': rule['risk_type'], 'title': rule['title'],
            'prediction_kind': 'rule', 'score': rounded(max(abs(z) for z in z_values), 3), 'score_meaning': Z_MEANING,
            'calibrated_probability': None, 'risk_level': rule_level(z_values, bool(rule.get('combined'))),
            'horizon_hours': rule.get('horizon_hours'), 'factors': with_contributions(factors) + context_factors,
            'data_quality': {indicator: quality['series'].get(indicator) for indicator in [item['indicator'] for item in factors]},
            'uncertainty': uncertainty(factors),
            'evidence': {'rule_version': config['version'], 'candidate_signal': bool(rule.get('combined')), 'combined_signal': bool(rule.get('combined')),
                         'statistical_threshold_z': statistics['deviation_z'],
                         'source_references': {item['indicator']: features[item['indicator']]['source_references'] for item in factors}},
        })
    return predictions, domain_state


def evaluate_anomalies(features, quality, config):
    statistics = config['statistics']
    predictions = []
    for indicator, settings in config['indicators'].items():
        if not settings.get('anomaly'):
            continue
        values = features.get(indicator) or {}
        score = values.get('latest_robust_z')
        if score is None or abs(score) < statistics['anomaly_robust_z']:
            continue
        predictions.append({
            'domain': settings['domain'], 'risk_type': f'anomaly_{indicator}', 'title': f'Statistical anomaly in {indicator.replace("_", " ")}',
            'prediction_kind': 'anomaly', 'score': rounded(score, 3), 'score_meaning': ANOMALY_MEANING, 'calibrated_probability': None,
            'risk_level': 'moderate' if abs(score) >= 2 * statistics['anomaly_robust_z'] else 'low', 'horizon_hours': 24,
            'factors': [{'indicator': indicator, 'direction': 'increase' if score > 0 else 'decrease', 'robust_z': rounded(score, 2),
                         'latest_value': values.get('latest_value'), 'latest_at': values.get('latest_at'),
                         'baseline_mean': values.get('baseline_mean'), 'baseline_source': values.get('baseline_source'), 'unit': values.get('unit')}],
            'data_quality': {indicator: quality['series'].get(indicator)},
            'uncertainty': {'level': 'high' if (values.get('baseline_n') or 0) < 10 else 'moderate', 'baseline_points': values.get('baseline_n'),
                            'note': 'A single anomalous reading may reflect measurement context. Confirm with a repeated measurement.'},
            'evidence': {'rule_version': config['version'], 'statistical_threshold_robust_z': statistics['anomaly_robust_z'],
                         'source_references': {indicator: values.get('source_references', [])[-1:]}},
        })
    return predictions


def evaluate_plan_targets(context, config):
    plan = context.get('nutrition_plan')
    settings = config['nutrition']
    if not plan or plan.get('energy_target_kcal') is None or plan.get('covered_days', 0) < settings['minimum_covered_days']:
        return []
    target = plan['energy_target_kcal']
    observed = plan['mean_daily_energy_kcal']
    if observed is None or observed >= target * (1 - settings['plan_shortfall_fraction']):
        return []
    shortfall = (target - observed) / target
    return [{
        'domain': 'nutrition', 'risk_type': 'nutrition_below_plan_target', 'title': 'Recorded energy intake below the nutritionist plan target',
        'prediction_kind': 'rule', 'score': rounded(shortfall, 3), 'score_meaning': 'Fractional shortfall of mean recorded daily energy against the active nutrition plan target. Not a probability.',
        'calibrated_probability': None, 'risk_level': 'moderate' if shortfall >= 2 * settings['plan_shortfall_fraction'] else 'low', 'horizon_hours': 72,
        'factors': [{'indicator': 'energy_intake', 'direction': 'decrease', 'mean_daily_kcal': rounded(observed, 1), 'plan_target_kcal': target, 'covered_days': plan['covered_days']}],
        'data_quality': {'energy_intake': 'meal_log_coverage', 'covered_days': plan['covered_days']},
        'uncertainty': {'level': 'moderate', 'note': 'Unlogged meals lower the recorded intake. Confirm meal logging completeness before acting.'},
        'evidence': {'rule_version': config['version'], 'nutrition_plan_id': plan.get('plan_id'), 'threshold_source': 'Active nutrition plan target approved by the mission nutritionist'},
    }]


def insufficient_predictions(domain_state, config):
    predictions = []
    for domain, state in sorted(domain_state.items()):
        if state['evaluable'] or state['signal']:
            continue
        predictions.append({
            'domain': domain, 'risk_type': f'{domain}_insufficient_data', 'title': f'Insufficient data for {domain} analysis',
            'prediction_kind': 'insufficient_data', 'score': None, 'score_meaning': None, 'calibrated_probability': None,
            'risk_level': 'undetermined', 'horizon_hours': None, 'factors': [],
            'data_quality': {'missing_or_without_baseline': sorted(state['missing'])},
            'uncertainty': {'level': 'not_assessable', 'note': 'Recent measurements or an individual baseline are missing. Absence of data is not treated as normal.'},
            'evidence': {'rule_version': config['version']},
        })
    for domain, settings in config['unavailable_domains'].items():
        predictions.append({
            'domain': domain, 'risk_type': f'{domain}_insufficient_data', 'title': settings['title'],
            'prediction_kind': 'insufficient_data', 'score': None, 'score_meaning': None, 'calibrated_probability': None,
            'risk_level': 'undetermined', 'horizon_hours': None, 'factors': [],
            'data_quality': {'missing_sources': settings['missing']},
            'uncertainty': {'level': 'not_assessable', 'note': 'The system does not store these records yet.'},
            'evidence': {'rule_version': config['version']},
        })
    return predictions
