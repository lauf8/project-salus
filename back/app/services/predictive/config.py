from functools import lru_cache
import json
import os
from pathlib import Path


CONFIG_DIRECTORY = Path(__file__).resolve().parents[2] / 'config'
ENGINE_VERSION = 'predictive-engine-v1'


@lru_cache
def rules_config():
    return json.loads((CONFIG_DIRECTORY / 'predictive_rules.json').read_text(encoding='utf-8'))


@lru_cache
def recommendation_catalog():
    return json.loads((CONFIG_DIRECTORY / 'recommendation_catalog.json').read_text(encoding='utf-8'))


def manual_cooldown_seconds():
    return max(0, int(os.getenv('PREDICTION_MANUAL_COOLDOWN_SECONDS', '300')))


def schedule_hours():
    return max(1, int(os.getenv('PREDICTION_SCHEDULE_HOURS', '6')))


def maximum_attempts():
    return max(1, int(os.getenv('PREDICTION_MAX_ATTEMPTS', '3')))
