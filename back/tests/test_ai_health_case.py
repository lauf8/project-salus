from datetime import datetime, timedelta, timezone

from scripts.create_ai_health_case import readings


def test_case_chronology_baselines_and_repeated_current_signals():
    reference = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    start = reference - timedelta(days=34)
    rows = readings(start, reference)
    assert all(at <= reference for at, *_ in rows)
    assert all(at < start for at, _, _, baseline, _ in rows if baseline)
    assert all(at >= start for at, _, _, baseline, _ in rows if not baseline)
    for indicator in ('heart_rate', 'respiratory_rate', 'oxygen_saturation', 'body_temperature'):
        recent = [row for row in rows if row[1] == indicator and reference - row[0] < timedelta(minutes=30)]
        assert len(recent) == 2
        assert all('shortness_of_breath' in row[4] for row in recent)
    assert min(row[2] for row in rows if row[1] == 'oxygen_saturation') == 90
    assert all(float(row[2]).is_integer() for row in rows if row[1] in ('sleep_duration', 'fatigue'))
