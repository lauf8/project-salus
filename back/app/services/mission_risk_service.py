from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlmodel import select

from app.models.mission_risks import MissionOccurrence, MissionRiskAction, MissionRiskAlert, MissionRiskEvaluation, MissionRiskPlan
from app.models.notifications import HealthNotification
from app.models.nutrition import FoodProduct, FoodStockMovement, MealLog, MealLogItem, MissionFoodLot
from app.models.preflight import Mission, MissionMember, utc_now
from app.models.user import User
from app.services.food_risk_rule import RISK_CATEGORIES, RULE_VERSION, project_food
from app.services.mission_rag import MissionRagService
from app.services.nutrition_service import as_utc, reference_amount
from app.services.preflight_service import PreflightService, transactional


class MissionRiskService(PreflightService):
    def writer(self, mission_id, lock=False):
        mission, actor = self._access(mission_id, {'mission_admin', 'nutritionist', 'flight_surgeon'}, lock=lock)
        if actor.role == 'flight_surgeon':
            self._require_physician()
        if actor.role == 'nutritionist' and not self.user.is_nutritionist:
            raise HTTPException(403, 'A nutritionist profile is required')
        return mission, actor

    def plan_at(self, mission_id, cutoff):
        return self.session.exec(select(MissionRiskPlan).where(MissionRiskPlan.mission_id == mission_id, MissionRiskPlan.recorded_at <= cutoff).order_by(MissionRiskPlan.recorded_at.desc(), MissionRiskPlan.id.desc())).first()

    def health_risks(self, mission_id):
        self._access(mission_id)
        from app.services.health_alert_service import HealthAlertService
        from app.services.clinical_risk_context import clinical_context
        service = HealthAlertService(self.session, self.user)
        astronauts = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.role == 'astronaut')).all()
        alerts = []
        visible_astronauts = 0
        for member in astronauts:
            try:
                service.authorize(member.user_id, mission_id)
            except HTTPException as exc:
                if exc.status_code == 403:
                    continue
                raise
            visible_astronauts += 1
            for page in range(1, 1001):
                response = service.list_alerts(member.user_id, mission_id, 'active', page, 100)
                for alert in response['data']:
                    observation = alert.latest_observation or alert.trigger_observation
                    alerts.append({
                        'id': alert.id, 'astronaut_id': member.user_id, 'indicator': alert.indicator,
                        'severity': alert.severity, 'status': alert.status, 'reason': alert.reason,
                        'collected_at': observation.collected_at, 'rule_version': alert.rule_version,
                        'verification_required': alert.verification_required,
                        'protocol_message': alert.protocol_message, 'context': clinical_context(alert),
                    })
                if not response['pagination']['has_next']:
                    break
        rank = {'critical': 0, 'urgent': 1, 'attention': 2}
        alerts.sort(key=lambda alert: (rank[alert['severity']], alert['astronaut_id'], alert['id']))
        return {'state': 'available' if visible_astronauts else 'restricted', 'alerts': alerts,
                'assessment_type': 'screening_signals', 'disease_probability_estimated': False,
                'notice': 'These are clinical screening signals, not confirmed diagnoses or forecasts of future disease. Clinical details follow existing health-record permissions.'}

    def plans(self, mission_id):
        self._access(mission_id)
        return self.session.exec(select(MissionRiskPlan).where(MissionRiskPlan.mission_id == mission_id).order_by(MissionRiskPlan.id.desc())).all()

    @transactional
    def save_plan(self, mission_id, payload):
        self.writer(mission_id, lock=True)
        if payload.coverage_end and payload.coverage_end > utc_now():
            raise HTTPException(422, 'Coverage cannot include future observations')
        rates = []
        for entry in payload.daily_rates:
            product = self._get(FoodProduct, entry.food_product_id)
            unit, quantity = entry.unit, entry.quantity
            if unit in {'kg', 'l', 'L'}:
                unit = 'g' if unit == 'kg' else 'ml'
                quantity *= 1000
            amount = quantity / reference_amount(product, unit, entry.basis)
            rates.append({**entry.model_dump(mode='json'), 'daily_references': str(amount * (payload.crew_size if entry.per_person else 1)),
                          'food_name': product.name, 'reference_unit': product.reference_unit, 'reference_quantity': str(product.reference_quantity)})
        for action in payload.approved_actions:
            self._get(FoodProduct, action.food_product_id)
        plan = MissionRiskPlan(mission_id=mission_id, author_user_id=self.user.id,
                               **payload.model_dump(exclude={'daily_rates', 'approved_actions'}),
                               daily_rates=rates, approved_actions=[a.model_dump() for a in payload.approved_actions])
        self.session.add(plan)
        self.session.flush()
        self.evaluate_internal(mission_id)
        return plan

    def occurrences(self, mission_id):
        self._access(mission_id)
        return self.session.exec(select(MissionOccurrence).where(MissionOccurrence.mission_id == mission_id).order_by(MissionOccurrence.event_at.desc())).all()

    @transactional
    def record_occurrence(self, mission_id, payload):
        self.writer(mission_id, lock=True)
        if payload.event_at > utc_now():
            raise HTTPException(422, 'An occurrence must describe an event that has already happened')
        if payload.category == 'food_shortage' and payload.food_product_id is None:
            raise HTTPException(422, 'Food shortage occurrences require a food product')
        if payload.food_product_id:
            self._get(FoodProduct, payload.food_product_id)
        if not all(reference.get('url') or reference.get('document_id') or reference.get('record_id') for reference in payload.source_references):
            raise HTTPException(422, 'Each source must identify a URL, document ID or verifiable record ID')
        occurrence = MissionOccurrence(mission_id=mission_id, author_user_id=self.user.id, **payload.model_dump())
        self.session.add(occurrence)
        self.session.flush()
        return occurrence

    @transactional
    def confirm_occurrence(self, mission_id, occurrence_id):
        self.writer(mission_id, lock=True)
        occurrence = self._get(MissionOccurrence, occurrence_id)
        if occurrence.mission_id != mission_id:
            raise HTTPException(404, 'Occurrence not found in this mission')
        if occurrence.confirmed_at is None:
            occurrence.confirmed_at = utc_now()
            occurrence.confirmed_by_user_id = self.user.id
            self.session.add(occurrence)
        return occurrence

    def stock_at(self, mission_id, cutoff, strict):
        rows = self.session.exec(select(FoodStockMovement, MissionFoodLot).join(MissionFoodLot, MissionFoodLot.id == FoodStockMovement.lot_id).where(MissionFoodLot.mission_id == mission_id, FoodStockMovement.recorded_at <= cutoff).order_by(FoodStockMovement.id)).all()
        lots = {}
        product_references = {}
        consumption = defaultdict(list)
        missing = []
        input_ids = []
        for movement, lot in rows:
            snapshot = movement.risk_snapshot
            if snapshot is None:
                if strict:
                    missing.append(f'Legacy movement {movement.id} has no immutable conversion/event snapshot')
                    continue
                product = self.session.get(FoodProduct, lot.food_product_id)
                legacy_event_at = as_utc(movement.recorded_at)
                if movement.meal_log_item_id:
                    meal_item = self.session.get(MealLogItem, movement.meal_log_item_id)
                    meal = self.session.get(MealLog, meal_item.meal_log_id)
                    legacy_event_at = as_utc(meal.consumed_at)
                snapshot = {'reference_delta': str(movement.quantity / reference_amount(product, lot.stock_unit, lot.stock_basis)),
                            'event_at': legacy_event_at.isoformat(), 'food_name': product.name,
                            'expiration_date': lot.expiration_date.isoformat(), 'unit': product.reference_unit,
                            'quantity_per_reference': str(product.reference_quantity)}
            event_at = as_utc(datetime.fromisoformat(snapshot['event_at']))
            if event_at > cutoff:
                continue
            target = product_references.setdefault(lot.food_product_id, snapshot)
            if snapshot['unit'] != target['unit']:
                missing.append(f'Incompatible reference units in movement {movement.id}')
                continue
            conversion = Decimal(snapshot['quantity_per_reference']) / Decimal(target['quantity_per_reference'])
            if lot.id not in lots:
                lots[lot.id] = {'id': lot.id, 'food_product_id': lot.food_product_id, 'quantity': Decimal(0),
                                'expiration_date': snapshot['expiration_date'], 'food_name': snapshot['food_name'],
                                'unit': target['unit'], 'quantity_per_reference': target['quantity_per_reference']}
            quantity = Decimal(snapshot['reference_delta']) * conversion
            lots[lot.id]['quantity'] += quantity
            input_ids.append(movement.id)
            if movement.movement_type in {'consumption', 'reversal'}:
                consumption[lot.food_product_id].append((event_at, -quantity, movement.id))
        return list(lots.values()), consumption, missing, input_ids

    def comparable_history(self, mission_id, plan, product_id, daily_rate, cutoff, reference=None):
        eligible = covered = affected = 0
        sources = []
        elapsed = max(timedelta(0), cutoff - as_utc(plan.exposure_start_at))
        remaining = as_utc(plan.planned_end_at) - max(cutoff, as_utc(plan.exposure_start_at))
        current_duration = as_utc(plan.planned_end_at) - as_utc(plan.exposure_start_at)
        missions = self.session.exec(select(Mission).where(Mission.id != mission_id)).all()
        for previous in missions:
            candidate = self.plan_at(previous.id, cutoff)
            if candidate is None or as_utc(candidate.planned_end_at) >= as_utc(plan.exposure_start_at):
                continue
            historical_evaluation = self.session.exec(select(MissionRiskEvaluation).where(
                MissionRiskEvaluation.mission_id == previous.id, MissionRiskEvaluation.recorded_at <= cutoff,
                MissionRiskEvaluation.state != 'replay',
            ).order_by(MissionRiskEvaluation.recorded_at.desc(), MissionRiskEvaluation.id.desc())).first()
            historical_mission = historical_evaluation.results.get('mission_snapshot', {}) if historical_evaluation else {}
            known_end = historical_mission.get('ended_at')
            if historical_mission.get('status') != 'completed' or known_end is None or as_utc(datetime.fromisoformat(known_end)) > cutoff:
                continue
            duration = as_utc(candidate.planned_end_at) - as_utc(candidate.exposure_start_at)
            rate_entry = next((row for row in candidate.daily_rates if row['food_product_id'] == product_id), None)
            current_entry = next((row for row in plan.daily_rates if row['food_product_id'] == product_id), None)
            if current_entry is None and reference is not None:
                current_entry = {'reference_unit': reference['unit'], 'reference_quantity': reference['quantity']}
            if daily_rate <= 0 or current_duration.total_seconds() <= 0:
                continue
            crew_ratio = candidate.crew_size / plan.crew_size
            duration_ratio = duration.total_seconds() / current_duration.total_seconds()
            interval_start = as_utc(candidate.exposure_start_at) + elapsed
            interval_end = interval_start + max(timedelta(0), remaining)
            if not (0.5 <= crew_ratio <= 2 and 0.5 <= duration_ratio <= 2) or interval_end > as_utc(candidate.planned_end_at):
                continue
            coverage = bool(candidate.inventory_complete and candidate.consumption_complete and candidate.coverage_start and candidate.coverage_end and as_utc(candidate.coverage_start) <= interval_start and as_utc(candidate.coverage_end) >= interval_end)
            rate = Decimal(rate_entry['daily_references']) if rate_entry else None
            if rate_entry and current_entry:
                if rate_entry['reference_unit'] != current_entry['reference_unit']:
                    coverage = False
                    rate = None
                else:
                    rate *= Decimal(rate_entry['reference_quantity']) / Decimal(current_entry['reference_quantity'])
            if rate is None and coverage:
                historical_lots, demand, gaps, _ = self.stock_at(previous.id, cutoff, strict=True)
                base = next((lot for lot in historical_lots if lot['food_product_id'] == product_id), None)
                if base and current_entry and base['unit'] == current_entry['reference_unit'] and not gaps:
                    observed = sum((amount for at, amount, _ in demand[product_id] if interval_start <= at <= interval_end), Decimal(0))
                    days = max(Decimal(1), Decimal(str((interval_end - interval_start).total_seconds() / 86400)))
                    rate = observed / days * Decimal(base['quantity_per_reference']) / Decimal(current_entry['reference_quantity'])
            if rate is not None:
                rate_ratio = (rate / candidate.crew_size) / (daily_rate / plan.crew_size)
                if not Decimal('0.5') <= rate_ratio <= 2:
                    continue
            eligible += 1
            if not coverage or rate is None:
                continue
            covered += 1
            occurrences = self.session.exec(select(MissionOccurrence).where(
                MissionOccurrence.mission_id == previous.id, MissionOccurrence.category == 'food_shortage',
                MissionOccurrence.food_product_id == product_id, MissionOccurrence.recorded_at <= cutoff,
                MissionOccurrence.confirmed_at.is_not(None), MissionOccurrence.confirmed_at <= cutoff,
                MissionOccurrence.event_at >= interval_start, MissionOccurrence.event_at <= interval_end,
            )).all()
            if occurrences:
                affected += 1
                sources.extend([{'id': row.id, 'mission_id': previous.id, 'event_at': as_utc(row.event_at).isoformat(),
                                 'references': row.source_references, 'actions': row.actions, 'outcome': row.outcome, 'intervention': row.intervention} for row in occurrences])
        return {'eligible_missions': eligible, 'sufficient_coverage_missions': covered, 'confirmed_occurrence_missions': affected,
                'frequency': f'{affected} of {covered} comparable missions with sufficient data' if covered else 'No comparable history with sufficient data',
                'criteria': 'Same food, prior completed missions, 0.5–2× crew and duration; 0.5–2× per-person demand when known; equivalent elapsed/remaining exposure. Sufficient coverage requires known comparable demand and declared inventory/consumption coverage.',
                'occurrences': sources}

    def calculate(self, mission_id, cutoff=None, replay=False):
        cutoff = as_utc(cutoff or utc_now())
        plan = self.plan_at(mission_id, cutoff)
        missing = []
        if plan is None:
            return {'state': 'inconclusive', 'missing_data': ['Versioned mission end, crew size and food planning'], 'items': [], 'input_references': {}, 'as_of': cutoff.isoformat()}
        if not replay:
            mission = self._get(Mission, mission_id)
            assigned_crew = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.role == 'astronaut')).all()
            if mission.crew_size is not None and mission.crew_size != plan.crew_size or len(assigned_crew) > plan.crew_size:
                missing.append('Update the versioned planning crew size to match the current mission')
        if not plan.inventory_complete:
            missing.append('Complete inventory declaration')
        if as_utc(plan.planned_end_at).date() < cutoff.date():
            missing.append('Mission planning horizon has ended')
        lots, consumption, stock_missing, movement_ids = self.stock_at(mission_id, cutoff, strict=replay)
        missing.extend(stock_missing)
        rates = {rate['food_product_id']: rate for rate in plan.daily_rates}
        product_ids = sorted({lot['food_product_id'] for lot in lots} | set(rates))
        if not product_ids:
            missing.append('Food products in inventory or meal planning')
        items = []
        window_end = datetime.combine(cutoff.date(), time.min, tzinfo=timezone.utc)
        window_start = window_end - timedelta(days=plan.consumption_window_days)
        projection_start = max(cutoff.date() + timedelta(days=1), as_utc(plan.exposure_start_at).date())
        for product_id in product_ids:
            product_lots = [lot for lot in lots if lot['food_product_id'] == product_id]
            planned = rates.get(product_id)
            reference_conflict = False
            demand_conversion = Decimal(1)
            if planned and product_lots:
                reference_conflict = any(lot['unit'] != planned['reference_unit'] for lot in product_lots)
                demand_conversion = Decimal(product_lots[0]['quantity_per_reference']) / Decimal(planned['reference_quantity'])
                for lot in product_lots:
                    lot['quantity'] *= demand_conversion
            name = planned['food_name'] if planned else product_lots[0]['food_name']
            used = sum((amount for occurred, amount, _ in consumption[product_id] if window_start <= occurred < window_end), Decimal(0)) * demand_conversion
            coverage = bool(plan.consumption_complete and plan.coverage_start and plan.coverage_end and as_utc(plan.coverage_start) <= window_start and as_utc(plan.coverage_end) >= window_end)
            observed_rate = max(Decimal(0), used) / Decimal(plan.consumption_window_days) if coverage else None
            planned_rate = Decimal(planned['daily_references']) if planned else None
            rate = max(v for v in [observed_rate, planned_rate] if v is not None) if observed_rate is not None or planned_rate is not None else None
            item_missing = list(missing)
            if reference_conflict:
                item_missing.append('Compatible food reference units between inventory and planning')
            if rate is None or rate <= 0:
                item_missing.append('Positive planned food demand or complete observed consumption window')
            if any(lot['quantity'] < 0 for lot in product_lots):
                item_missing.append('Consistent stock movement balance')
            item = {'food_product_id': product_id, 'food_name': name, 'current_balance': str(sum((lot['quantity'] for lot in product_lots if lot['expiration_date'] >= cutoff.date().isoformat()), Decimal(0))),
                    'quantity_unit': 'food reference portions', 'reference': {'unit': planned['reference_unit'] if planned else product_lots[0]['unit'], 'quantity': planned['reference_quantity'] if planned else product_lots[0]['quantity_per_reference']},
                    'daily_rate': str(rate) if rate is not None else None, 'planned_daily_rate': str(planned_rate) if planned_rate is not None else None,
                    'observed_daily_rate': str(observed_rate) if observed_rate is not None else None,
                    'consumption_source': 'maximum of planned and fully covered observed demand',
                    'consumption_window': {'start': window_start.isoformat(), 'end': window_end.isoformat(), 'coverage_confirmed': coverage},
                    'missing_data': item_missing, 'state': 'inconclusive' if item_missing else 'evaluated',
                    'first_shortage_date': None, 'severity': 'none', 'daily_projection': []}
            if not item_missing:
                item.update(project_food(product_lots, rate, projection_start, as_utc(plan.planned_end_at).date()))
                item['state'] = 'risk' if item['first_shortage_date'] else 'sufficient'
            item['history'] = self.comparable_history(mission_id, plan, product_id, rate or Decimal(0), cutoff, item['reference'])
            items.append(item)
        return {'state': 'inconclusive' if missing or any(item['state'] == 'inconclusive' for item in items) else 'evaluated',
                'missing_data': sorted(set(missing)), 'items': items, 'as_of': cutoff.isoformat(), 'horizon': as_utc(plan.planned_end_at).isoformat(),
                'input_references': {'plan_id': plan.id, 'movement_ids': movement_ids, 'lot_ids': [lot['id'] for lot in lots]},
                'mission_snapshot': {'status': mission.status, 'ended_at': as_utc(mission.ended_at).isoformat() if mission.ended_at else None} if not replay else None,
                'rule_version': RULE_VERSION, 'projection_assumption': 'Full daily demand from the next UTC day; preflight from planned exposure start. Expiration day remains usable.'}

    def notify(self, alert):
        if alert.responsible_user_id is None:
            return
        existing = self.session.exec(select(HealthNotification).where(HealthNotification.risk_alert_id == alert.id, HealthNotification.recipient_user_id == alert.responsible_user_id)).first()
        if existing is None:
            self.session.add(HealthNotification(recipient_user_id=alert.responsible_user_id, mission_id=alert.mission_id,
                                               risk_alert_id=alert.id, title='Mission food shortage risk',
                                               message='Review the mission Risks tab and verify food inventory before the projected shortage.'))

    def evaluate_internal(self, mission_id, notify=True):
        self.session.exec(select(Mission).where(Mission.id == mission_id).with_for_update()).one()
        self.session.flush()
        now = utc_now()
        result = self.calculate(mission_id, now)
        horizon = datetime.fromisoformat(result['horizon']) if result.get('horizon') else None
        evaluation = MissionRiskEvaluation(mission_id=mission_id, rule_version=RULE_VERSION, evaluated_at=now, horizon=horizon, state=result['state'], results=result)
        self.session.add(evaluation)
        self.session.flush()
        active = self.session.exec(select(MissionRiskAlert).where(MissionRiskAlert.mission_id == mission_id, MissionRiskAlert.risk_type == 'food_shortage', MissionRiskAlert.status != 'resolved')).all()
        by_product = {alert.food_product_id: alert for alert in active}
        members = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.role.in_(['mission_admin', 'nutritionist']))).all()
        members.sort(key=lambda member: (member.role != 'nutritionist', member.id))
        for item in result['items']:
            alert = by_product.get(item['food_product_id'])
            if item['state'] == 'risk':
                due = datetime.combine(datetime.fromisoformat(item['first_shortage_date']).date(), time.min, tzinfo=timezone.utc)
                if alert is None:
                    alert = MissionRiskAlert(mission_id=mission_id, food_product_id=item['food_product_id'], evaluation_id=evaluation.id,
                                             severity=item['severity'], due_at=due, responsible_user_id=members[0].user_id if members else self.user.id,
                                             guidance={'state': 'pending', 'action': 'Verify usable lot counts, expiration dates and replenishment options with mission control.', 'sources': [], 'documentary_evidence': False})
                if alert.evaluation_id != evaluation.id:
                    alert.guidance = {'state': 'pending', 'action': 'Verify usable lot counts, expiration dates and replenishment options with mission control.', 'sources': [], 'documentary_evidence': False}
                if alert.due_at != due:
                    alert.read_at = None
                alert.evaluation_id = evaluation.id
                alert.severity = item['severity']
                alert.due_at = due
                alert.updated_at = now
                self.session.add(alert)
                self.session.flush()
                if notify:
                    self.notify(alert)
            elif item['state'] == 'sufficient' and alert is not None:
                alert.status = 'resolved'
                alert.outcome = 'Stock projection is sufficient after updated inventory/planning; this does not confirm an occurrence.'
                alert.updated_at = now
                self.session.add(alert)
                self.session.add(MissionRiskAction(alert_id=alert.id, actor_user_id=self.user.id, action='automatic_resolution', details=alert.outcome))
        self.session.flush()
        return evaluation

    @transactional
    def evaluate(self, mission_id):
        self.writer(mission_id, lock=True)
        return self.evaluate_internal(mission_id)

    def list_state(self, mission_id):
        _, actor = self._access(mission_id)
        evaluation = self.session.exec(select(MissionRiskEvaluation).where(MissionRiskEvaluation.mission_id == mission_id, MissionRiskEvaluation.state != 'replay').order_by(MissionRiskEvaluation.id.desc())).first()
        alerts = self.session.exec(select(MissionRiskAlert).where(MissionRiskAlert.mission_id == mission_id).order_by(MissionRiskAlert.updated_at.desc())).all()
        if actor.role == 'astronaut':
            alerts = [alert for alert in alerts if alert.responsible_user_id == self.user.id]
        alert_rows = []
        for alert in alerts:
            source_evaluation = self._get(MissionRiskEvaluation, alert.evaluation_id)
            item = next((row for row in source_evaluation.results['items'] if row['food_product_id'] == alert.food_product_id), None)
            row = self.alert_response(alert, actor.role == 'astronaut')
            alert_rows.append({**row, 'assessment': item})
        return {'evaluation': evaluation, 'alerts': alert_rows, 'categories': RISK_CATEGORIES,
                'can_manage': actor.role in {'mission_admin', 'nutritionist', 'flight_surgeon'}}

    @transactional
    def guidance(self, mission_id, alert_id):
        self.writer(mission_id)
        alert = self._get(MissionRiskAlert, alert_id)
        if alert.mission_id != mission_id:
            raise HTTPException(404, 'Risk alert not found')
        evaluation = self._get(MissionRiskEvaluation, alert.evaluation_id)
        item = next(row for row in evaluation.results['items'] if row['food_product_id'] == alert.food_product_id)
        plan = self._get(MissionRiskPlan, evaluation.results['input_references']['plan_id'])
        approved = next((row for row in plan.approved_actions if row['food_product_id'] == alert.food_product_id), None)
        context = {'risk_type': 'food_shortage', 'food_name': item['food_name'], 'shortage_date': item['first_shortage_date'],
                   'daily_reference_portions': item['daily_rate'], 'history_counts': {key: item['history'][key] for key in ['eligible_missions', 'sufficient_coverage_missions', 'confirmed_occurrence_missions']}}
        fallback = {'state': 'no_documentary_evidence', 'action': approved['action'] if approved else 'Verify usable lot counts, expiration dates and replenishment options with mission control.',
                    'sources': [], 'documentary_evidence': False, 'approved_operational_action': approved, 'due_at': alert.due_at.isoformat(), 'suggested_responsible_role': 'nutritionist'}
        try:
            rag = MissionRagService(self.session)
            sources = rag.search(f"NASA food inventory storage shelf life food shortage prevention {item['food_name']}")
            if sources:
                generated = rag.rag.generate(context, sources)
                used_ids = set(generated['citation_ids'])
                fallback.update({'state': 'documented', 'action': approved['action'] if approved else generated['action'],
                                 'sources': [source for source in sources if source['id'] in used_ids], 'documentary_evidence': True,
                                 'suggested_responsible_role': generated['responsible_role'], 'generated_action': generated['action'], 'review_state': 'approved_operational' if approved else 'pending_review'})
        except Exception:
            fallback['state'] = 'rag_unavailable'
        alert = self.session.exec(select(MissionRiskAlert).where(MissionRiskAlert.id == alert.id).with_for_update().execution_options(populate_existing=True)).one()
        if alert.evaluation_id != evaluation.id:
            raise HTTPException(409, 'The assessment changed; request updated guidance')
        alert.guidance = fallback
        alert.updated_at = utc_now()
        self.session.add(alert)
        return alert

    @transactional
    def action(self, mission_id, alert_id, payload):
        _, actor = self._access(mission_id, lock=True)
        alert = self._get(MissionRiskAlert, alert_id)
        if alert.mission_id != mission_id:
            raise HTTPException(404, 'Risk alert not found')
        manager = actor.role in {'mission_admin', 'nutritionist', 'flight_surgeon'}
        assigned = alert.responsible_user_id == self.user.id
        if not manager and not (actor.role == 'astronaut' and assigned and payload.action in {'read', 'execute'}):
            raise HTTPException(403, 'Only the responsible astronaut or mission team can perform this action')
        now = utc_now()
        if payload.action == 'approve_guidance':
            if not alert.guidance.get('generated_action'):
                raise HTTPException(409, 'Retrieve generated guidance before reviewing it')
            if payload.guidance_kind == 'clinical' and not self.user.is_physician:
                raise HTTPException(403, 'Clinical guidance requires physician review')
            alert.guidance = {**alert.guidance, 'review_state': 'approved', 'guidance_kind': payload.guidance_kind,
                              'reviewed_by_user_id': self.user.id, 'reviewed_at': now.isoformat()}
        elif payload.action == 'assign':
            member = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.user_id == payload.responsible_user_id)).first()
            if member is None or member.role not in {'astronaut', 'mission_admin', 'nutritionist', 'flight_surgeon'}:
                raise HTTPException(422, 'Choose an astronaut or authorized operational mission team member')
            alert.responsible_user_id = member.user_id
            self.notify(alert)
        elif payload.action == 'read':
            alert.read_at = now
            if alert.status == 'open':
                alert.status = 'acknowledged'
            notifications = self.session.exec(select(HealthNotification).where(HealthNotification.risk_alert_id == alert.id, HealthNotification.recipient_user_id == self.user.id)).all()
            for notification in notifications:
                notification.read_at = now
                self.session.add(notification)
        elif payload.action == 'execute':
            if alert.status == 'resolved':
                raise HTTPException(409, 'The alert is already resolved')
            alert.executed_at = now
            alert.status = 'executed'
        elif payload.action == 'resolve':
            alert.outcome = payload.details
            alert.status = 'resolved'
        alert.updated_at = now
        self.session.add(alert)
        self.session.add(MissionRiskAction(alert_id=alert.id, actor_user_id=self.user.id, action=payload.action, details=payload.details))
        return alert

    def actions(self, mission_id, alert_id):
        _, actor = self._access(mission_id)
        alert = self._get(MissionRiskAlert, alert_id)
        if alert.mission_id != mission_id or actor.role == 'astronaut' and alert.responsible_user_id != self.user.id:
            raise HTTPException(404, 'Risk alert not found')
        return self.session.exec(select(MissionRiskAction).where(MissionRiskAction.alert_id == alert_id).order_by(MissionRiskAction.id)).all()

    def alert_response(self, alert, astronaut=False):
        values = alert.model_dump()
        guidance = dict(alert.guidance)
        if astronaut and guidance.get('generated_action') and guidance.get('review_state') not in {'approved', 'approved_operational'}:
            guidance = {'state': 'awaiting_team_review', 'review_state': 'pending_review', 'documentary_evidence': False,
                        'action': 'Verify usable lot counts, expiration dates and replenishment options with mission control.', 'sources': []}
        values['guidance'] = guidance
        return values

    def assigned(self):
        membership = select(MissionMember.mission_id).where(MissionMember.user_id == self.user.id)
        alerts = self.session.exec(select(MissionRiskAlert).where(MissionRiskAlert.mission_id.in_(membership), MissionRiskAlert.responsible_user_id == self.user.id, MissionRiskAlert.status != 'resolved').order_by(MissionRiskAlert.due_at)).all()
        return [self.alert_response(alert, astronaut=self.user.is_astronaut) for alert in alerts]

    @transactional
    def replay(self, mission_id, start_at, end_at):
        mission, _ = self.writer(mission_id)
        if mission.ended_at is None or end_at > as_utc(mission.ended_at) or end_at > utc_now():
            raise HTTPException(422, 'Replay requires a completed mission and dates through its actual end')
        chronology = []
        day = start_at
        while day <= end_at:
            result = self.calculate(mission_id, day, replay=True)
            for item in result['items']:
                item.pop('daily_projection', None)
            chronology.append(result)
            day += timedelta(days=1)
        confirmed = self.session.exec(select(MissionOccurrence).where(MissionOccurrence.mission_id == mission_id, MissionOccurrence.category == 'food_shortage', MissionOccurrence.confirmed_at.is_not(None), MissionOccurrence.event_at >= start_at, MissionOccurrence.event_at <= end_at)).all()
        first_alerts = {}
        for result in chronology:
            for item in result['items']:
                if item['state'] == 'risk':
                    first_alerts.setdefault(item['food_product_id'], datetime.fromisoformat(result['as_of']))
        detected, missed, lead_times = [], [], []
        for occurrence in confirmed:
            predicted = first_alerts.get(occurrence.food_product_id)
            if predicted is not None and predicted <= as_utc(occurrence.event_at):
                detected.append(occurrence.id)
                lead_times.append({'occurrence_id': occurrence.id, 'lead_days': (as_utc(occurrence.event_at) - predicted).total_seconds() / 86400})
            else:
                missed.append(occurrence.id)
        matched = {occurrence.food_product_id for occurrence in confirmed}
        actions = self.session.exec(select(MissionRiskAction).join(MissionRiskAlert).where(MissionRiskAlert.mission_id == mission_id, MissionRiskAction.action == 'execute')).all()
        report = {'mission_id': mission_id, 'chronology': chronology, 'detected_occurrences': detected, 'missed_occurrences': missed,
                'lead_times': lead_times, 'alerts_without_confirmed_occurrence': [product for product in first_alerts if product not in matched],
                'interventions': [{'occurrence_id': row.id, 'food_product_id': row.food_product_id, 'source': 'confirmed occurrence'} for row in confirmed if row.intervention] + [{'action_id': row.id, 'alert_id': row.alert_id, 'food_product_id': self.session.get(MissionRiskAlert, row.alert_id).food_product_id, 'recorded_at': row.recorded_at.isoformat(), 'source': 'executed action'} for row in actions if as_utc(row.recorded_at) <= end_at],
                'notifications_sent': 0, 'rule_version': RULE_VERSION,
                'outcome_note': 'Final confirmed occurrences are scoring labels only. Each prediction uses only immutable records available by its cutoff. Unconfirmed alerts are not automatically false positives.'}
        run = MissionRiskEvaluation(mission_id=mission_id, rule_version=RULE_VERSION, evaluated_at=end_at, horizon=end_at, state='replay', results=report)
        self.session.add(run)
        self.session.flush()
        return {**report, 'report_id': run.id}
