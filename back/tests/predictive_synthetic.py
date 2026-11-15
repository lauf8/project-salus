"""Synthetic records for predictive tests. They are not clinical or operational validation data."""

from datetime import datetime, timedelta, timezone
import random

from app.services.predictive.features import Measurement


START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def point(series, value, at, reference_id, unit=None, delay_minutes=5, preflight=False):
    return Measurement(series=series, value=float(value), at=at, recorded_at=at + timedelta(minutes=delay_minutes), unit=unit,
                       source='synthetic', reference=('synthetic', reference_id), is_preflight_reference=preflight)


def steady_series(series, values, start=START, hour=8, unit=None, first_id=1):
    return [point(series, value, start + timedelta(days=index, hours=hour), first_id + index, unit) for index, value in enumerate(values)]


def episodes(generator, days):
    in_episode, fatigue_high = [False] * days, [False] * days
    day = 0
    while day < days:
        if generator.random() < 0.08:
            length = generator.choice([3, 4])
            for offset in range(length):
                if day + offset < days:
                    in_episode[day + offset] = True
            for offset in range(1, length + 1):
                if day + offset < days:
                    fatigue_high[day + offset] = True
            day += length + 2
        else:
            day += 1
    return in_episode, fatigue_high


def fatigue_cohort(astronauts=6, days=120, seed=11):
    generator = random.Random(seed)
    cohort = {}
    reference = 1
    for astronaut in range(1, astronauts + 1):
        records = []
        in_episode, fatigue_high = episodes(generator, days)
        for day in range(days):
            sleep = generator.gauss(300, 25) if in_episode[day] else generator.gauss(450, 20)
            fatigue = generator.choice([7, 8, 9]) if fatigue_high[day] else generator.choice([2, 3, 3, 4])
            heart_rate = generator.gauss(70 if in_episode[day] else 64, 3)
            stress = generator.choice([3, 4]) if in_episode[day] else generator.choice([2, 2, 3])
            morning = START + timedelta(days=day)
            records.append(point('sleep_duration', round(sleep), morning + timedelta(hours=7), reference, 'min'))
            records.append(point('fatigue', fatigue, morning + timedelta(hours=8), reference + 1, '0-10'))
            records.append(point('resting_heart_rate', round(heart_rate, 1), morning + timedelta(hours=8, minutes=30), reference + 2, 'bpm'))
            records.append(point('mental_stress', stress, morning + timedelta(hours=20), reference + 3, '1-5'))
            reference += 4
        cohort[astronaut] = records
    return cohort
