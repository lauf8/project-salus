from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import math

from app.services.predictive.features import aware, build_features, model_vector


FEATURE_METRICS = ('mean_24h', 'mean_7d', 'z_7d', 'slope_per_day', 'hours_since_last')
FEATURE_SERIES = ('sleep_duration', 'sleep_quality', 'fatigue', 'resting_heart_rate', 'mental_stress', 'mental_workload', 'mental_energy')
FEATURE_NAMES = tuple(f'{series}.{metric}' for series in FEATURE_SERIES for metric in FEATURE_METRICS)
MINIMUM_TRAINING_SAMPLES = 200
MINIMUM_TRAINING_POSITIVES = 20
MINIMUM_TEST_POSITIVES = 10
MAXIMUM_MISSING_FEATURE_RATIO = 0.4
MAXIMUM_CALIBRATION_ERROR = 0.1
MINIMUM_PR_AUC_GAIN = 0.05
MINIMUM_RECALL = 0.5


@dataclass(frozen=True)
class OutcomeDefinition:
    name: str
    series: str
    horizon_hours: int
    description: str


ELEVATED_FATIGUE_24H = OutcomeDefinition(
    name='elevated_fatigue_24h', series='fatigue', horizon_hours=24,
    description='At least one self-reported fatigue rating in the next 24 hours at or above the individual baseline mean plus two baseline standard deviations, with the baseline computed only from data available at prediction time.',
)
OUTCOMES = {ELEVATED_FATIGUE_24H.name: ELEVATED_FATIGUE_24H}


def outcome_label(records, as_of, baseline_values, outcome):
    if baseline_values is None:
        return None
    mean_value, std_value = baseline_values
    if std_value is None or std_value == 0:
        return None
    threshold = mean_value + 2 * std_value
    future = [record for record in records if record.series == outcome.series and as_of < aware(record.at) <= as_of + timedelta(hours=outcome.horizon_hours)]
    if not future:
        return None
    return int(any(record.value >= threshold for record in future))


def sample_times(records, start, end):
    days = sorted({aware(record.at).date() for record in records if start <= aware(record.at) <= end})
    return [datetime.combine(day, time(12), tzinfo=timezone.utc) for day in days]


def build_dataset(records_by_subject, config, outcome=ELEVATED_FATIGUE_24H):
    rows = []
    for subject_id, records in records_by_subject.items():
        if not records:
            continue
        start = min(aware(record.at) for record in records)
        end = max(aware(record.at) for record in records) - timedelta(hours=outcome.horizon_hours)
        for as_of in sample_times(records, start, end):
            features, quality = build_features(records, as_of, config, list(FEATURE_SERIES))
            target = features[outcome.series]
            baseline = (target['baseline_mean'], target['baseline_std']) if target['baseline_mean'] is not None else None
            label = outcome_label(records, as_of, baseline, outcome)
            if label is None:
                continue
            vector = model_vector(features, FEATURE_NAMES)
            missing = sum(1 for value in vector if math.isnan(value)) / len(vector)
            if missing > MAXIMUM_MISSING_FEATURE_RATIO:
                continue
            recent = [record for record in records if record.series == outcome.series and as_of - timedelta(hours=outcome.horizon_hours) < aware(record.at) <= as_of]
            persistence = int(any(record.value >= baseline[0] + 2 * baseline[1] for record in recent)) if recent else 0
            rows.append({'subject_id': subject_id, 'as_of': as_of, 'vector': vector, 'label': label, 'persistence': persistence})
    rows.sort(key=lambda row: (row['as_of'], row['subject_id']))
    return rows


def temporal_split(rows, test_fraction=0.3):
    if not rows:
        return [], []
    times = sorted({row['as_of'] for row in rows})
    cutoff = times[int(len(times) * (1 - test_fraction))] if len(times) > 1 else times[-1]
    train = [row for row in rows if row['as_of'] < cutoff]
    test = [row for row in rows if row['as_of'] >= cutoff]
    return train, test


def expected_calibration_error(labels, probabilities, bins=10):
    total = len(labels)
    error = 0.0
    reliability = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [(label, probability) for label, probability in zip(labels, probabilities) if low <= probability < high or (index == bins - 1 and probability == 1)]
        if not members:
            continue
        observed = sum(label for label, _ in members) / len(members)
        predicted = sum(probability for _, probability in members) / len(members)
        error += len(members) / total * abs(observed - predicted)
        reliability.append({'bin': [low, high], 'count': len(members), 'mean_predicted': round(predicted, 4), 'observed_rate': round(observed, 4)})
    return error, reliability


def classification_metrics(labels, probabilities, threshold=0.5):
    from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, f1_score, precision_score, recall_score
    predicted = [int(probability >= threshold) for probability in probabilities]
    tn, fp, fn, tp = confusion_matrix(labels, predicted, labels=[0, 1]).ravel()
    ece, reliability = expected_calibration_error(labels, probabilities)
    return {
        'precision': round(float(precision_score(labels, predicted, zero_division=0)), 4),
        'recall': round(float(recall_score(labels, predicted, zero_division=0)), 4),
        'f1': round(float(f1_score(labels, predicted, zero_division=0)), 4),
        'pr_auc': round(float(average_precision_score(labels, probabilities)), 4) if len(set(labels)) > 1 else None,
        'brier': round(float(brier_score_loss(labels, probabilities)), 4),
        'expected_calibration_error': round(ece, 4), 'reliability': reliability,
        'false_negatives': int(fn), 'false_positives': int(fp), 'true_positives': int(tp), 'true_negatives': int(tn),
        'threshold': threshold, 'n': len(labels), 'positives': int(sum(labels)),
    }


def baseline_metrics(train, test):
    prevalence = sum(row['label'] for row in train) / len(train)
    labels = [row['label'] for row in test]
    persistence = [0.9 * row['persistence'] + 0.1 * prevalence for row in test]
    return {'prevalence': classification_metrics(labels, [prevalence] * len(test)), 'persistence': classification_metrics(labels, persistence)}


def candidate_estimators():
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return {
        'logistic_regression': make_pipeline(SimpleImputer(strategy='median', add_indicator=True), StandardScaler(),
                                             CalibratedClassifierCV(LogisticRegression(max_iter=1000), method='sigmoid', cv=3)),
        'random_forest': make_pipeline(SimpleImputer(strategy='median', add_indicator=True),
                                       CalibratedClassifierCV(RandomForestClassifier(n_estimators=200, min_samples_leaf=5, random_state=7), method='isotonic', cv=3)),
    }


def gate(metrics, baselines, data_summary):
    reasons = []
    if data_summary['train_samples'] < MINIMUM_TRAINING_SAMPLES:
        reasons.append(f"Training samples {data_summary['train_samples']} below {MINIMUM_TRAINING_SAMPLES}")
    if data_summary['train_positives'] < MINIMUM_TRAINING_POSITIVES:
        reasons.append(f"Training positives {data_summary['train_positives']} below {MINIMUM_TRAINING_POSITIVES}")
    if data_summary['test_positives'] < MINIMUM_TEST_POSITIVES:
        reasons.append(f"Test positives {data_summary['test_positives']} below {MINIMUM_TEST_POSITIVES}")
    if metrics is None:
        return False, reasons or ['No model was trained']
    best_baseline_pr = max((value['pr_auc'] or 0) for value in baselines.values())
    best_baseline_brier = min(value['brier'] for value in baselines.values())
    if metrics['pr_auc'] is None or metrics['pr_auc'] < best_baseline_pr + MINIMUM_PR_AUC_GAIN:
        reasons.append('PR-AUC does not exceed the best simple baseline by the required margin')
    if metrics['brier'] >= best_baseline_brier:
        reasons.append('Brier score is not better than the best simple baseline')
    if metrics['expected_calibration_error'] > MAXIMUM_CALIBRATION_ERROR:
        reasons.append('Calibration error exceeds the allowed maximum')
    if metrics['recall'] < MINIMUM_RECALL:
        reasons.append('Recall is below the minimum; false negatives are too frequent')
    return not reasons, reasons


def train_outcome_model(records_by_subject, config, outcome=ELEVATED_FATIGUE_24H):
    rows = build_dataset(records_by_subject, config, outcome)
    train, test = temporal_split(rows)
    summary = {'samples': len(rows), 'train_samples': len(train), 'test_samples': len(test),
               'train_positives': sum(row['label'] for row in train), 'test_positives': sum(row['label'] for row in test),
               'subjects': len({row['subject_id'] for row in rows}),
               'split': 'temporal: the most recent 30% of prediction times form the test set',
               'train_end': train[-1]['as_of'].isoformat() if train else None, 'test_start': test[0]['as_of'].isoformat() if test else None}
    result = {'outcome': outcome.name, 'outcome_description': outcome.description, 'horizon_hours': outcome.horizon_hours,
              'feature_names': list(FEATURE_NAMES), 'data': summary, 'candidates': {}, 'selected': None, 'baselines': None,
              'passed': False, 'reasons': [], 'artifact': None}
    enough = summary['train_samples'] >= MINIMUM_TRAINING_SAMPLES and summary['train_positives'] >= MINIMUM_TRAINING_POSITIVES and summary['test_positives'] >= MINIMUM_TEST_POSITIVES and len({row['label'] for row in train}) == 2
    if not enough:
        result['passed'], result['reasons'] = gate(None, {}, summary)
        result['reasons'] = result['reasons'] or ['Training data contains a single class']
        return result
    import joblib
    x_train = [row['vector'] for row in train]
    y_train = [row['label'] for row in train]
    x_test = [row['vector'] for row in test]
    y_test = [row['label'] for row in test]
    baselines = baseline_metrics(train, test)
    result['baselines'] = baselines
    best_name, best_estimator, best_metrics = None, None, None
    for name, estimator in candidate_estimators().items():
        estimator.fit(x_train, y_train)
        probabilities = [float(value) for value in estimator.predict_proba(x_test)[:, 1]]
        metrics = classification_metrics(y_test, probabilities)
        result['candidates'][name] = metrics
        if best_metrics is None or (metrics['pr_auc'] or 0) > (best_metrics['pr_auc'] or 0):
            best_name, best_estimator, best_metrics = name, estimator, metrics
    passed, reasons = gate(best_metrics, baselines, summary)
    result.update({'selected': best_name, 'passed': passed, 'reasons': reasons, 'metrics': best_metrics})
    buffer = BytesIO()
    joblib.dump({'estimator': best_estimator, 'feature_names': list(FEATURE_NAMES), 'outcome': outcome.name}, buffer)
    result['artifact'] = buffer.getvalue()
    result['artifact_sha256'] = sha256(result['artifact']).hexdigest()
    return result


def load_artifact(model):
    import joblib
    if model.artifact is None or sha256(model.artifact).hexdigest() != model.artifact_sha256:
        raise ValueError('Model artifact is missing or does not match its recorded hash')
    return joblib.load(BytesIO(model.artifact))


def infer(model, features):
    payload = load_artifact(model)
    vector = model_vector(features, payload['feature_names'])
    missing = sum(1 for value in vector if math.isnan(value)) / len(vector)
    if missing > MAXIMUM_MISSING_FEATURE_RATIO:
        return None, missing
    probability = float(payload['estimator'].predict_proba([vector])[0][1])
    return probability, missing


def probability_level(probability, prevalence):
    if probability >= max(0.5, 2 * prevalence):
        return 'high'
    if probability >= max(0.25, 1.5 * prevalence):
        return 'moderate'
    return 'low'
