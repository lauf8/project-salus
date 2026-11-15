from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
from statistics import mean, median, pstdev


@dataclass(frozen=True)
class Measurement:
    series: str
    value: float
    at: datetime
    recorded_at: datetime
    unit: str | None = None
    source: str | None = None
    reference: tuple[str, int] | None = None
    is_preflight_reference: bool = False
    context: dict = field(default_factory=dict, compare=False, hash=False)


def aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def available_at(records, as_of):
    as_of = aware(as_of)
    return [record for record in records if aware(record.at) <= as_of and aware(record.recorded_at) <= as_of]


def rounded(value, digits=4):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return round(value, digits)


def linear_slope_per_day(points):
    if len(points) < 3:
        return None
    origin = points[0].at
    xs = [(point.at - origin).total_seconds() / 86400 for point in points]
    ys = [point.value for point in points]
    x_mean, y_mean = mean(xs), mean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator


def window(points, as_of, days, end_offset_days=0):
    end = as_of - timedelta(days=end_offset_days)
    start = end - timedelta(days=days)
    return [point for point in points if start < aware(point.at) <= end]


def summary(values):
    if not values:
        return None
    return mean(values)


def individual_baseline(points, as_of, stats):
    preflight = [point for point in points if point.is_preflight_reference]
    if len(preflight) >= stats['minimum_preflight_points']:
        return preflight, 'preflight_reference'
    far, near = stats['baseline_window_days']
    historical = [point for point in points if not point.is_preflight_reference and as_of - timedelta(days=far) < aware(point.at) <= as_of - timedelta(days=near)]
    if len(historical) >= stats['minimum_baseline_points']:
        return historical, 'individual_history'
    return [], None


def robust_z(value, values):
    if len(values) < 3:
        return None
    center = median(values)
    mad = median([abs(item - center) for item in values])
    if mad == 0:
        return None
    return 0.6745 * (value - center) / mad


def series_features(points, as_of, stats):
    as_of = aware(as_of)
    ordered = sorted(available_at(points, as_of), key=lambda point: (aware(point.at), point.reference or ('', 0)))
    in_mission = [point for point in ordered if not point.is_preflight_reference]
    last_24h = window(in_mission, as_of, 1)
    last_7d = window(in_mission, as_of, 7)
    previous_7d = window(in_mission, as_of, 7, end_offset_days=7)
    last_30d = window(in_mission, as_of, 30)
    trend_points = window(in_mission, as_of, stats['trend_window_days'])
    baseline_points, baseline_source = individual_baseline(ordered, as_of, stats)
    baseline_values = [point.value for point in baseline_points]
    baseline_mean = mean(baseline_values) if baseline_values else None
    baseline_std = pstdev(baseline_values) if len(baseline_values) >= 2 else None
    values_30d = [point.value for point in last_30d]
    mean_7d = summary([point.value for point in last_7d])
    mean_previous_7d = summary([point.value for point in previous_7d])
    z_7d = None
    if mean_7d is not None and baseline_mean is not None and baseline_std:
        z_7d = (mean_7d - baseline_mean) / baseline_std
    latest = in_mission[-1] if in_mission else None
    changes = None
    if baseline_std and len(last_30d) >= 2:
        steps = [abs(b.value - a.value) for a, b in zip(last_30d, last_30d[1:])]
        changes = sum(1 for step in steps if step > baseline_std) / len(steps)
    latest_robust_z = robust_z(latest.value, baseline_values) if latest is not None and aware(latest.at) > as_of - timedelta(days=1) else None
    return {
        'n_24h': len(last_24h), 'n_7d': len(last_7d), 'n_30d': len(last_30d),
        'mean_24h': rounded(summary([point.value for point in last_24h])),
        'mean_7d': rounded(mean_7d),
        'mean_30d': rounded(summary(values_30d)),
        'std_30d': rounded(pstdev(values_30d) if len(values_30d) >= 2 else None),
        'min_30d': rounded(min(values_30d) if values_30d else None),
        'max_30d': rounded(max(values_30d) if values_30d else None),
        'slope_per_day': rounded(linear_slope_per_day(trend_points)),
        'pct_change_7d': rounded((mean_7d - mean_previous_7d) / abs(mean_previous_7d) * 100 if mean_7d is not None and mean_previous_7d else None),
        'baseline_mean': rounded(baseline_mean), 'baseline_std': rounded(baseline_std),
        'baseline_n': len(baseline_values), 'baseline_source': baseline_source,
        'diff_from_baseline': rounded(mean_7d - baseline_mean if mean_7d is not None and baseline_mean is not None else None),
        'z_7d': rounded(z_7d),
        'change_frequency': rounded(changes),
        'latest_value': rounded(latest.value) if latest else None,
        'latest_at': aware(latest.at).isoformat() if latest else None,
        'latest_robust_z': rounded(latest_robust_z),
        'hours_since_last': rounded((as_of - aware(latest.at)).total_seconds() / 3600, 2) if latest else None,
        'unit': latest.unit if latest else (ordered[-1].unit if ordered else None),
        'source_references': [list(point.reference) for point in last_30d if point.reference],
    }


def build_features(records, as_of, config, series_names=None):
    as_of = aware(as_of)
    stats = config['statistics']
    names = series_names or list(config['indicators'])
    grouped = {name: [] for name in names}
    for record in records:
        if record.series in grouped:
            grouped[record.series].append(record)
    features = {name: series_features(points, as_of, stats) for name, points in grouped.items()}
    quality = data_quality(features, stats)
    return features, quality


def data_quality(features, stats):
    per_series = {}
    for name, values in features.items():
        if values['n_7d'] == 0:
            state = 'missing'
        elif values['n_7d'] < stats['minimum_window_points']:
            state = 'sparse'
        elif values['baseline_source'] is None:
            state = 'no_baseline'
        elif values['hours_since_last'] is not None and values['hours_since_last'] > stats['staleness_hours']:
            state = 'stale'
        else:
            state = 'sufficient'
        per_series[name] = state
    total = len(per_series) or 1
    missing = sum(1 for state in per_series.values() if state == 'missing')
    usable = sum(1 for state in per_series.values() if state == 'sufficient')
    return {'series': per_series, 'missing_ratio': round(missing / total, 4), 'usable_ratio': round(usable / total, 4), 'usable_series': usable, 'total_series': total}


def deviation(values, direction, threshold, minimum_points):
    z = values.get('z_7d')
    if values.get('n_7d', 0) < minimum_points:
        return None
    if z is None:
        return False if values.get('baseline_std') == 0 and values.get('diff_from_baseline') == 0 else None
    if direction == 'increase' and z >= threshold:
        return z
    if direction == 'decrease' and z <= -threshold:
        return z
    if direction == 'any' and abs(z) >= threshold:
        return z
    return False


def model_vector(features, feature_names):
    vector = []
    for name in feature_names:
        series, metric = name.rsplit('.', 1)
        value = features.get(series, {}).get(metric)
        vector.append(float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else math.nan)
    return vector
