from datetime import date, timedelta
from decimal import Decimal


RULE_VERSION = 'food-fefo-v1'
RISK_CATEGORIES = {
    'food_shortage': {'implemented': True, 'clinical_review_required': False},
    'sleep_fatigue': {'implemented': False, 'missing': ['versioned sleep and duty periods'], 'clinical_review_required': True},
    'physical_fitness': {'implemented': False, 'missing': ['reviewed longitudinal fitness assessments'], 'clinical_review_required': True},
    'well_being': {'implemented': False, 'missing': ['non-identifiable reviewed indicators'], 'clinical_review_required': True},
    'spacecraft': {'implemented': False, 'missing': ['module telemetry and validated failure rules'], 'clinical_review_required': False},
}


def project_food(lots, daily_rate, start_day, end_day):
    rate = Decimal(str(daily_rate))
    balances = [dict(lot, quantity=Decimal(str(lot['quantity']))) for lot in sorted(lots, key=lambda row: (row['expiration_date'], row['id']))]
    days = []
    first_shortage = None
    current = start_day
    while current <= end_day:
        expired = Decimal(0)
        for lot in balances:
            if date.fromisoformat(str(lot['expiration_date'])) < current:
                expired += lot['quantity']
                lot['quantity'] = Decimal(0)
        available = sum((lot['quantity'] for lot in balances), Decimal(0))
        demand = rate
        allocations = []
        for lot in balances:
            taken = min(lot['quantity'], demand)
            if taken:
                lot['quantity'] -= taken
                demand -= taken
                allocations.append({'lot_id': lot['id'], 'quantity': str(taken)})
        if demand > 0 and first_shortage is None:
            first_shortage = current
        days.append({'date': current.isoformat(), 'opening_balance': str(available), 'demand': str(rate),
                     'expired': str(expired), 'unmet': str(demand), 'balance': str(sum((lot['quantity'] for lot in balances), Decimal(0))), 'allocations': allocations})
        current += timedelta(days=1)
    lead_days = (first_shortage - start_day).days if first_shortage else None
    return {'first_shortage_date': first_shortage.isoformat() if first_shortage else None,
            'severity': ('critical' if lead_days <= 3 else 'warning') if lead_days is not None else 'none',
            'daily_projection': days}
