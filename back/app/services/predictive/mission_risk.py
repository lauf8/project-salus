from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import os

from sqlmodel import select

from app.models.mission_risks import MissionOccurrence
from app.models.nutrition import FoodStockMovement, MissionFoodLot
from app.models.predictive import FeatureSnapshot, PredictionRun, RiskPrediction
from app.models.preflight import Mission, MissionMember
from app.models.spacecraft import Spacecraft, SpacecraftModule
from app.services.predictive.config import rules_config
from app.services.predictive.features import aware, rounded
from app.services.predictive.data_collection import mission_status_at


def insufficient(domain, risk_type, title, missing, note):
    return {'domain': domain, 'risk_type': risk_type, 'title': title, 'prediction_kind': 'insufficient_data', 'score': None,
            'score_meaning': None, 'calibrated_probability': None, 'risk_level': 'undetermined', 'horizon_hours': None, 'factors': [],
            'data_quality': {'missing_sources': missing}, 'uncertainty': {'level': 'not_assessable', 'note': note}, 'evidence': {}}


def as_float(value):
    return float(Decimal(str(value))) if value is not None else None


def supply_summary(item, as_of_day, end_day):
    rate = as_float(item.get('daily_rate'))
    balance = as_float(item.get('current_balance'))
    rates = [value for value in (as_float(item.get('planned_daily_rate')), as_float(item.get('observed_daily_rate'))) if value]
    remaining_days = max(0, (end_day - as_of_day).days) if end_day else None
    summary = {'food_product_id': item['food_product_id'], 'food_name': item['food_name'], 'state': item['state'],
               'current_balance': rounded(balance, 3), 'unit': item.get('quantity_unit'), 'daily_rate': rounded(rate, 3),
               'planned_daily_rate': rounded(as_float(item.get('planned_daily_rate')), 3), 'observed_daily_rate': rounded(as_float(item.get('observed_daily_rate')), 3),
               'estimated_depletion_date': item.get('first_shortage_date'), 'missing_data': item.get('missing_data', [])}
    if rate and balance is not None:
        summary['days_of_stock'] = rounded(balance / rate, 1)
        summary['days_of_stock_range'] = [rounded(balance / max(rates), 1), rounded(balance / min(rates), 1)] if rates else None
        if remaining_days is not None:
            required = rate * remaining_days
            summary['required_until_end'] = rounded(required, 3)
            summary['safety_margin'] = rounded(balance - required, 3)
            summary['safety_margin_days'] = rounded(balance / rate - remaining_days, 1)
    return summary


class MissionRiskPredictionService:
    def __init__(self, session, config=None):
        self.session = session
        self.config = config or rules_config()

    def latest_astronaut_runs(self, mission_id, as_of=None):
        members = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.role == 'astronaut')).all()
        runs = {}
        for member in members:
            run = self.session.exec(select(PredictionRun).where(PredictionRun.subject_type == 'astronaut', PredictionRun.subject_id == member.user_id,
                                                                PredictionRun.mission_id == mission_id, PredictionRun.status == 'completed',
                                                                PredictionRun.as_of <= (as_of or datetime.now().astimezone())).order_by(PredictionRun.as_of.desc(), PredictionRun.id.desc())).first()
            runs[member.user_id] = run
        return members, runs

    def collect(self, mission_id, as_of):
        from app.services.mission_risk_service import MissionRiskService
        mission = self.session.get(Mission, mission_id)
        food_service = MissionRiskService(self.session, None)
        food = food_service.calculate(mission_id, as_of, replay=True)
        lots = self.session.exec(select(MissionFoodLot).where(MissionFoodLot.mission_id == mission_id)).all()
        stock, _, _, _ = food_service.stock_at(mission_id, as_of, strict=True)
        balances = {row['id']: row for row in stock}
        movements = self.session.exec(select(FoodStockMovement).where(FoodStockMovement.lot_id.in_(list(balances)), FoodStockMovement.recorded_at <= as_of)).all() if balances else []
        quantities = defaultdict(Decimal)
        for movement in movements:
            if movement.risk_snapshot and aware(datetime.fromisoformat(movement.risk_snapshot['event_at'])) <= aware(as_of):
                quantities[movement.lot_id] += movement.quantity
        lots = [lot.model_copy(update={'remaining_quantity': quantities[lot.id], 'expiration_date': date.fromisoformat(balances[lot.id]['expiration_date'])}) for lot in lots if lot.id in balances]
        occurrences = self.session.exec(select(MissionOccurrence).where(MissionOccurrence.mission_id == mission_id, MissionOccurrence.recorded_at <= as_of, MissionOccurrence.event_at <= as_of, MissionOccurrence.confirmed_at <= as_of)).all()
        members, runs = self.latest_astronaut_runs(mission_id, as_of)
        astronaut_predictions = {}
        astronaut_features = {}
        for user_id, run in runs.items():
            if run is None:
                continue
            astronaut_predictions[user_id] = self.session.exec(select(RiskPrediction).where(RiskPrediction.run_id == run.id)).all()
            snapshot = self.session.get(FeatureSnapshot, run.feature_snapshot_id) if run.feature_snapshot_id else None
            astronaut_features[user_id] = snapshot.features if snapshot else {}
        similar = []
        if mission.spacecraft_id:
            similar = self.session.exec(select(MissionOccurrence).join(Mission, Mission.id == MissionOccurrence.mission_id).where(
                Mission.spacecraft_id == mission.spacecraft_id, Mission.id != mission_id, MissionOccurrence.confirmed_at.is_not(None),
                MissionOccurrence.recorded_at <= as_of, MissionOccurrence.event_at <= as_of, MissionOccurrence.confirmed_at <= as_of)).all()
        data = {'mission': mission, 'food': food, 'lots': lots, 'occurrences': occurrences, 'members': members, 'runs': runs,
                'astronaut_predictions': astronaut_predictions, 'astronaut_features': astronaut_features, 'similar_occurrences': similar}
        key = json.dumps({'food': food.get('input_references'), 'food_state': [(item['food_product_id'], item['state'], item.get('first_shortage_date')) for item in food['items']],
                          'lots': sorted((lot.id, str(lot.remaining_quantity), lot.expiration_date.isoformat()) for lot in lots),
                          'occurrences': sorted((row.id, bool(row.confirmed_at)) for row in occurrences), 'runs': sorted((uid, run.id if run else None) for uid, run in runs.items()),
                          'similar': sorted(row.id for row in similar), 'status': mission.status, 'ended_at': str(mission.ended_at)}, sort_keys=True, default=str)
        return data, sha256(key.encode()).hexdigest()

    def predict(self, data, as_of):
        as_of = aware(as_of)
        mission = data['mission']
        food = data['food']
        end_day = date.fromisoformat(food['horizon'][:10]) if food.get('horizon') else None
        predictions = []
        supplies = [supply_summary(item, as_of.date(), end_day) for item in food['items']]
        for item, summary in zip(food['items'], supplies):
            if item['state'] == 'risk':
                lead = (date.fromisoformat(item['first_shortage_date']) - as_of.date()).days
                predictions.append({
                    'domain': 'supplies', 'risk_type': 'food_shortage', 'title': f"Projected shortage of {item['food_name']}",
                    'prediction_kind': 'rule', 'score': lead, 'score_meaning': 'Days until the first projected unmet daily demand. Not a probability.',
                    'calibrated_probability': None, 'risk_level': 'high' if item['severity'] == 'critical' else 'moderate',
                    'horizon_hours': max(0, lead) * 24, 'factors': [summary],
                    'data_quality': {'consumption_window_confirmed': item['consumption_window']['coverage_confirmed'], 'missing_data': item['missing_data']},
                    'uncertainty': {'level': 'moderate', 'days_of_stock_range': summary.get('days_of_stock_range'),
                                    'note': 'The projection uses the maximum of planned and fully covered observed demand. Consumption variation shifts the depletion date.'},
                    'evidence': {'rule_version': food.get('rule_version'), 'history': item.get('history'), 'food_product_id': item['food_product_id']},
                })
        if not food['items'] or food['state'] == 'inconclusive' and not any(item['state'] == 'risk' for item in food['items']):
            predictions.append(insufficient('supplies', 'food_supply_insufficient_data', 'Food supply projection', food.get('missing_data') or ['Food inventory and planned demand'],
                                            'The food projection is inconclusive until the listed data exists.'))
        predictions.extend(self.expiration(data['lots'], as_of, end_day))
        predictions.append(insufficient('supplies', 'medicine_supply_insufficient_data', 'Medicine stock projection', ['Mission medicine inventory', 'Medicine dispensing ledger'],
                                        'Medication uses are recorded, but no mission medicine stock exists. No shortage is estimated.'))
        predictions.extend(self.collective(data))
        predictions.extend(self.recurrence(data['occurrences'], 'recurring_occurrence', 'mission'))
        context = {'mission_status': mission_status_at(mission, as_of), 'crew_size': mission.crew_size, 'astronauts': len(data['members']),
                   'duration': self.duration(mission, food, as_of), 'supplies': supplies,
                   'occurrences': self.occurrence_summary(data['occurrences']), 'similar_mission_occurrences': self.occurrence_summary(data['similar_occurrences']),
                   'astronauts_analyzed': sum(1 for run in data['runs'].values() if run is not None)}
        return predictions, context

    def duration(self, mission, food, as_of):
        started = aware(mission.started_at) if mission.started_at else None
        planned_end = food.get('horizon')
        result = {'started_at': started.isoformat() if started else None, 'ended_at': aware(mission.ended_at).isoformat() if mission.ended_at and aware(mission.ended_at) <= aware(as_of) else None, 'planned_end_at': planned_end}
        if started:
            result['elapsed_days'] = rounded((as_of - started).total_seconds() / 86400, 1)
        if started and planned_end:
            result['planned_days'] = rounded((aware(datetime.fromisoformat(planned_end)) - started).total_seconds() / 86400, 1)
        return result

    def expiration(self, lots, as_of, end_day):
        warning = max(0, int(os.getenv('FOOD_EXPIRATION_WARNING_DAYS', '7')))
        limit = as_of.date() + timedelta(days=warning)
        expiring = [lot for lot in lots if lot.remaining_quantity > 0 and as_of.date() <= lot.expiration_date and (lot.expiration_date <= limit or end_day and lot.expiration_date < end_day)]
        if not expiring:
            return []
        rows = [{'lot_id': lot.id, 'food_product_id': lot.food_product_id, 'lot_code': lot.lot_code, 'expiration_date': lot.expiration_date.isoformat(),
                 'remaining_quantity': str(lot.remaining_quantity), 'stock_unit': lot.stock_unit, 'before_mission_end': bool(end_day and lot.expiration_date < end_day)} for lot in expiring]
        soon = [row for row in rows if date.fromisoformat(row['expiration_date']) <= limit]
        return [{'domain': 'supplies', 'risk_type': 'food_expiration', 'title': 'Food lots expiring before use or mission end', 'prediction_kind': 'rule',
                 'score': len(rows), 'score_meaning': 'Number of lots with remaining stock that expire within the warning window or before the planned mission end.',
                 'calibrated_probability': None, 'risk_level': 'moderate' if soon else 'low', 'horizon_hours': warning * 24, 'factors': rows,
                 'data_quality': {'source': 'mission_food_lots current balance'}, 'uncertainty': {'level': 'low', 'note': 'Expiration dates are recorded values; consumption before expiry is not projected per lot.'},
                 'evidence': {'warning_days': warning, 'warning_source': 'FOOD_EXPIRATION_WARNING_DAYS'}}]

    def collective(self, data):
        settings = self.config['collective']
        analyzed = [uid for uid, run in data['runs'].items() if run is not None]
        if len(analyzed) < settings['minimum_affected_astronauts']:
            return [insufficient('crew_health', 'collective_health_insufficient_data', 'Collective crew health trends', ['Recent individual analyses for at least two astronauts'],
                                 'Collective trends need individual analyses of several crew members.')]
        results = []
        for risk_type, title, types in (('collective_fatigue', 'Concurrent fatigue or sleep signals across the crew', set(settings['fatigue_risk_types'])),
                                        ('collective_wellbeing_decline', 'Concurrent wellbeing signals across the crew', set(settings['wellbeing_risk_types']))):
            affected = [uid for uid in analyzed if any(row.risk_type in types and row.prediction_kind in ('rule', 'ml', 'anomaly') for row in data['astronaut_predictions'].get(uid, []))]
            result = self.collective_result(risk_type, title, affected, analyzed, settings)
            if result:
                results.append(result)
        indicator = settings['workload_indicator']
        threshold = self.config['statistics']['deviation_z']
        elevated = [uid for uid in analyzed if (data['astronaut_features'].get(uid, {}).get(indicator, {}).get('z_7d') or 0) >= threshold]
        result = self.collective_result('collective_workload', 'Concurrent workload increase across the crew', elevated, analyzed, settings)
        if result:
            results.append(result)
        return results

    def collective_result(self, risk_type, title, affected, analyzed, settings):
        fraction = len(affected) / len(analyzed)
        if len(affected) < settings['minimum_affected_astronauts'] or fraction < settings['minimum_affected_fraction']:
            return None
        return {'domain': 'crew_health', 'risk_type': risk_type, 'title': title, 'prediction_kind': 'rule', 'score': rounded(fraction, 3),
                'score_meaning': 'Fraction of analyzed astronauts with a concurrent individual signal. Not a probability.', 'calibrated_probability': None,
                'risk_level': 'high' if fraction >= 0.75 else 'moderate', 'horizon_hours': 72,
                'factors': [{'affected_astronauts': len(affected), 'analyzed_astronauts': len(analyzed)}],
                'data_quality': {'analyzed_astronauts': len(analyzed)},
                'uncertainty': {'level': 'moderate', 'note': 'Aggregated from individual signals; individual details follow health-record permissions.'},
                'evidence': {'aggregation': 'counts only', 'minimum_affected_astronauts': settings['minimum_affected_astronauts'], 'minimum_affected_fraction': settings['minimum_affected_fraction']}}

    def recurrence(self, occurrences, risk_type, scope):
        confirmed = [row for row in occurrences if row.confirmed_at is not None]
        minimum = self.config['occurrences']['minimum_recurrences']
        by_category = defaultdict(list)
        for row in confirmed:
            by_category[row.category].append(row)
        results = []
        for category, rows in sorted(by_category.items()):
            if len(rows) < minimum:
                continue
            results.append({'domain': 'operations', 'risk_type': risk_type, 'title': f'Recurring confirmed {category.replace("_", " ")} occurrences ({scope})',
                            'prediction_kind': 'rule', 'score': len(rows), 'score_meaning': 'Number of confirmed occurrences in the same category. Not a probability.',
                            'calibrated_probability': None, 'risk_level': 'moderate' if len(rows) >= 2 * minimum else 'low', 'horizon_hours': None,
                            'factors': [{'category': category, 'occurrences': len(rows), 'missions': len({row.mission_id for row in rows})}],
                            'data_quality': {'confirmed_only': True}, 'uncertainty': {'level': 'high', 'note': 'Recurrence counts describe history; they do not estimate when a new occurrence will happen.'},
                            'evidence': {'occurrence_ids': [row.id for row in rows], 'actions': [row.actions for row in rows][:5]}})
        return results

    def occurrence_summary(self, occurrences):
        counts = Counter(row.category for row in occurrences)
        confirmed = Counter(row.category for row in occurrences if row.confirmed_at is not None)
        return [{'category': category, 'recorded': total, 'confirmed': confirmed.get(category, 0)} for category, total in sorted(counts.items())]


class SpacecraftRiskPredictionService(MissionRiskPredictionService):
    def collect_spacecraft(self, spacecraft_id, as_of):
        spacecraft = self.session.get(Spacecraft, spacecraft_id)
        modules = self.session.exec(select(SpacecraftModule).where(SpacecraftModule.spacecraft_id == spacecraft_id)).all()
        missions = self.session.exec(select(Mission).where(Mission.spacecraft_id == spacecraft_id, Mission.planned_launch_at <= as_of).order_by(Mission.planned_launch_at)).all()
        occurrences = self.session.exec(select(MissionOccurrence).where(MissionOccurrence.mission_id.in_([mission.id for mission in missions]), MissionOccurrence.recorded_at <= as_of, MissionOccurrence.event_at <= as_of, MissionOccurrence.confirmed_at <= as_of)).all() if missions else []
        key = json.dumps({'modules': sorted(module.id for module in modules), 'missions': sorted((m.id, m.status) for m in missions), 'occurrences': sorted((o.id, bool(o.confirmed_at)) for o in occurrences)})
        return {'spacecraft': spacecraft, 'modules': modules, 'missions': missions, 'occurrences': occurrences}, sha256(key.encode()).hexdigest()

    def predict_spacecraft(self, data, as_of):
        spacecraft = data['spacecraft']
        missions = data['missions']
        predictions = [insufficient('spacecraft', 'technical_failure_insufficient_data', 'Technical failure prediction',
                                    ['Module telemetry', 'Failure and maintenance history', 'Validated failure definitions'],
                                    'No telemetry or failure records exist. No failure estimate is produced.')]
        predictions.extend(self.recurrence(data['occurrences'], 'spacecraft_recurring_occurrence', 'spacecraft history'))
        usage_days = 0.0
        for mission in missions:
            if mission.started_at:
                end = min(aware(mission.ended_at), aware(as_of)) if mission.ended_at else aware(as_of)
                usage_days += max(0.0, (end - aware(mission.started_at)).total_seconds() / 86400)
        context = {'spacecraft': {'id': spacecraft.id, 'name': spacecraft.name, 'manufacturer': spacecraft.manufacturer, 'model': spacecraft.model,
                                  'manufactured_year': spacecraft.manufactured_year, 'status': 'in_use' if any(mission_status_at(mission, as_of) == 'in_progress' for mission in missions) else 'available', 'maximum_crew_capacity': spacecraft.maximum_crew_capacity},
                   'modules': [{'id': module.id, 'code': module.code, 'name': module.name, 'is_pressurized': module.is_pressurized, 'is_habitable': module.is_habitable,
                                'technical_specifications': module.technical_specifications} for module in data['modules']],
                   'usage': {'missions': len(missions), 'completed_missions': sum(1 for m in missions if mission_status_at(m, as_of) == 'completed'), 'usage_days': rounded(usage_days, 1),
                             'mission_ids': [mission.id for mission in missions]},
                   'occurrences': self.occurrence_summary(data['occurrences'])}
        return predictions, context
