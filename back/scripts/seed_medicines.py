import argparse
import json
import unicodedata
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, select

from app.database import engine
from app.models.medicines import ActiveIngredient, Medicine, MedicineActiveIngredient


CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data' / 'common_medicines.json'


def identity(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


def load_catalog(path=CATALOG_PATH):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    entries = payload['medicines']
    names = set()
    for entry in entries:
        name = identity(entry['name'])
        ingredients = [identity(value) for value in entry['active_ingredients']]
        if not name or name in names or not ingredients or not all(ingredients) or len(ingredients) != len(set(ingredients)):
            raise ValueError('The catalog contains invalid or duplicate names or compositions')
        if not entry['main_indications'].strip() or not set(entry['markets']) <= {'US', 'BR'}:
            raise ValueError('The catalog contains invalid indications or countries')
        names.add(name)
    for market in ('US', 'BR'):
        if sum(market in entry['markets'] for entry in entries) != 100:
            raise ValueError(f'The catalog must contain exactly 100 medications for {market}')
    return payload


def seed_catalog(session, catalog):
    existing_medicines = {}
    existing_ingredients = {}
    for model, index in ((Medicine, existing_medicines), (ActiveIngredient, existing_ingredients)):
        for row in session.exec(select(model)).all():
            key = identity(row.name)
            if key in index:
                raise ValueError(f'The existing records contain duplicate names: {row.name}')
            index[key] = row
    counts = {'medicines_created': 0, 'ingredients_created': 0, 'medicines_reused': 0, 'indications_filled': 0}
    for entry in catalog['medicines']:
        ingredient_ids = []
        for name in entry['active_ingredients']:
            key = identity(name)
            ingredient = existing_ingredients.get(key)
            if ingredient is None:
                ingredient = ActiveIngredient(name=name)
                session.add(ingredient)
                session.flush()
                existing_ingredients[key] = ingredient
                counts['ingredients_created'] += 1
            ingredient_ids.append(ingredient.id)
        medicine = existing_medicines.get(identity(entry['name']))
        if medicine is None:
            medicine = Medicine(name=entry['name'], main_indications=entry['main_indications'])
            session.add(medicine)
            session.flush()
            for ingredient_id in ingredient_ids:
                session.add(MedicineActiveIngredient(medicine_id=medicine.id, active_ingredient_id=ingredient_id))
            existing_medicines[identity(entry['name'])] = medicine
            counts['medicines_created'] += 1
        else:
            links = session.exec(select(MedicineActiveIngredient).where(MedicineActiveIngredient.medicine_id == medicine.id)).all()
            if {link.active_ingredient_id for link in links} != set(ingredient_ids):
                raise ValueError(f'Existing composition differs for {medicine.name}; no data was imported')
            if not medicine.main_indications:
                medicine.main_indications = entry['main_indications']
                session.add(medicine)
                counts['indications_filled'] += 1
            counts['medicines_reused'] += 1
    session.flush()
    return counts


def main():
    parser = argparse.ArgumentParser(description='Import the catalog of common medications in the United States and Brazil')
    parser.add_argument('--path', type=Path, default=CATALOG_PATH)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    catalog = load_catalog(args.path)
    with Session(engine) as session:
        try:
            session.exec(text('SELECT pg_advisory_xact_lock(742306102)'))
            result = seed_catalog(session, catalog)
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
        except Exception:
            session.rollback()
            raise
    print(json.dumps({**result, 'dry_run': args.dry_run, 'market_counts': {market: sum(market in entry['markets'] for entry in catalog['medicines']) for market in ('US', 'BR')}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
