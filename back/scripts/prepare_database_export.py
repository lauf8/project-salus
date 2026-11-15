import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import unicodedata

from sqlalchemy import JSON, bindparam, inspect, text
from sqlmodel import Session, select

from app.database import engine
from app.models.preflight import Mission, MissionMember
from app.models.spacecraft import Spacecraft, SpacecraftModule
from app.models.user import User


FIRST_NAMES = ('André', 'Ana', 'Bruno', 'Carolina', 'Daniel', 'Eduarda', 'Felipe', 'Gabriela', 'Gustavo', 'Isabela', 'João', 'Júlia', 'Leonardo', 'Letícia', 'Lucas', 'Luiza', 'Marcelo', 'Marina', 'Pedro', 'Renata', 'Ricardo', 'Sofia', 'Vinícius', 'Vitória', 'Caio')
LAST_NAMES = ('Almeida', 'Barros', 'Cardoso', 'Ferreira', 'Lacerda', 'Moraes', 'Pereira', 'Ribeiro', 'Santana', 'Teixeira')
PROGRAMS = ('Aurora', 'Horizonte', 'Meridiano', 'Órbita', 'Alvorada', 'Travessia', 'Vanguarda', 'Nascente', 'Atlântico', 'Cruzeiro')
STAFF_NAMES = {'flight_surgeon': 'Helena Monteiro', 'mission_admin': 'Rafael Andrade', 'psychologist': 'Mariana Azevedo', 'nutritionist': 'Camila Duarte', 'nurse': 'Thiago Menezes', 'observer': 'Beatriz Nogueira'}
MARKER = re.compile(r'\b(?:synthetic|sintétic[oa]s?|sintetic[oa]s?|fictíci[oa]s?|fictici[oa]s?|fictional|ficcional|ficcionais|simulation|simulated|demo|demonstration|simulação|simulacao|simulator)\b', re.IGNORECASE)
PHRASES = {
    'Avaliação ficcional registrada para simulação.': 'Avaliação pré-voo concluída e registrada.',
    'Registro clínico ficcional.': 'Avaliação clínica registrada no prontuário.',
    'Condição preexistente ficcional.': 'Condição preexistente informada na avaliação pré-voo.',
    'Reavaliação ficcional concluída.': 'Reavaliação concluída após acompanhamento.',
    'Registro de simulação': 'Registro de administração conforme orientação médica',
    'Dose ficcional registrada': 'Conforme prescrição registrada',
    'Acompanhamento ficcional da semana.': 'Revisão semanal de adaptação, descanso e convivência.',
    'Plano alimentar ficcional.': 'Plano alimentar ajustado às necessidades energéticas e à rotina de missão.',
    'Revisão operacional ficcional.': 'Revisão operacional e verificação dos procedimentos de bordo.',
    'Salus Alert Demonstration — Synthetic Data': 'Horizonte — Operação de Suporte',
    'Refeição composta sintética': 'Arroz integral com frango e legumes',
    'Medicamento sintético A': 'Medicação de uso eventual',
    'Ingrediente sintético A': 'Princípio ativo registrado',
    'Salus Synthetic': 'Centro Aeroespacial Nacional',
    'Salus Demo Mission Admin': 'Rodrigo Freitas',
    'Salus Demo Physician': 'Clara Machado',
    'Salus Demo Astronaut 1': 'Henrique Tavares',
    'Salus Demo Astronaut 2': 'Laura Campos',
    '!synthetic-public-demo': '!',
    'synthetic:': 'record:',
    'simulation-only': 'mission-specific',
    'Simulator 1': 'Tripulada Classe A',
    'Simulator 2': 'Tripulada Classe B',
    'Simulator 3': 'Tripulada Classe C',
    'alerts-demo-admin@salus.example': 'rodrigo.freitas@crew.salus.example',
    'alerts-demo-physician@salus.example': 'clara.machado@crew.salus.example',
    'alerts-demo-astronaut-1@salus.example': 'henrique.tavares@crew.salus.example',
    'alerts-demo-astronaut-2@salus.example': 'laura.campos@crew.salus.example',
}


def person_name(index):
    return f'{FIRST_NAMES[index % len(FIRST_NAMES)]} {LAST_NAMES[index // len(FIRST_NAMES)]}'


def mission_name(index):
    return f'{PROGRAMS[index // 5]} {index % 5 + 1:02d}'


def email_for(name):
    normalized = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return '.'.join(normalized.split()) + '@crew.salus.example'


def clean_value(value, replacements):
    if isinstance(value, str):
        if value == 'simulation' or value.startswith('simulation-'):
            return value
        result = value
        for old, new in replacements:
            result = result.replace(old, new)
        if MARKER.search(result):
            result = MARKER.sub('', result)
            result = re.sub(r'[ \t]{2,}', ' ', result).strip(' ·—:-')
        return result
    if isinstance(value, list):
        return [clean_value(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: item if key in ('id', 'profile_id', 'rule_version', 'catalog', 'indicator', 'status', 'state', 'role', 'code') else clean_value(item, replacements) for key, item in value.items()}
    return value


def prepare(args):
    if os.getenv('SALUS_SYNTHETIC_ENV') not in ('development', 'test') or any(os.getenv(key, '').lower() in ('prod', 'production') for key in ('APP_ENV', 'ENVIRONMENT', 'ENV')):
        raise RuntimeError('Only development and test databases are supported')
    source = json.loads(Path(args.manifest).read_text())
    registry_path = Path(args.registry)
    if registry_path.exists():
        registry = json.loads(registry_path.read_text())
        with Session(engine) as session:
            for row in registry['missions']:
                mission = session.get(Mission, row['id'])
                if mission is None or mission.name != row['name']:
                    raise RuntimeError('Presentation registry does not match application records')
        print(json.dumps({'status': 'already_prepared', 'missions': len(registry['missions'])}))
        return
    mission_ids = [row['mission_id'] for row in source['cases']]
    if len(set(mission_ids)) != 50:
        raise ValueError('The source manifest must identify exactly 50 missions')
    registry = {'configuration': source['configuration'], 'data_origin': 'generated fictional development data; not real clinical or spaceflight records',
                'source_manifest_sha256': sha256(Path(args.manifest).read_bytes()).hexdigest(),
                'prepared_at': datetime.now(timezone.utc).isoformat(), 'missions': [], 'users': [], 'spacecraft': [], 'changed_columns': []}
    with engine.begin() as connection:
        connection.execute(text('SET LOCAL search_path TO public'))
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('salus-synthetic-50-v1:public'))"))
        with Session(connection, join_transaction_mode='create_savepoint') as session:
            missions = session.exec(select(Mission).where(Mission.id.in_(mission_ids)).order_by(Mission.id)).all()
            if len(missions) != 50 or any(not row.name.startswith('Salus Synthetic ') for row in missions):
                raise RuntimeError('The selected mission set does not match the original published cohort')
            replacements = dict(PHRASES)
            for index, row in enumerate(missions):
                replacements[row.name] = mission_name(index)
                registry['missions'].append({'id': row.id, 'original_name': row.name, 'name': mission_name(index)})
            members = session.exec(select(MissionMember).where(MissionMember.mission_id.in_(mission_ids))).all()
            astronaut_ids = sorted({row.user_id for row in members if row.role == 'astronaut'})
            staff_roles = {row.user_id: row.role for row in members if row.role != 'astronaut'}
            people = session.exec(select(User).where(User.id.in_(astronaut_ids + list(staff_roles)))).all()
            proposed_emails = []
            for person in people:
                name = person_name(astronaut_ids.index(person.id)) if person.id in astronaut_ids else STAFF_NAMES[staff_roles[person.id]]
                email = email_for(name)
                replacements[person.name] = name
                replacements[person.email] = email
                proposed_emails.append(email)
                registry['users'].append({'id': person.id, 'original_name': person.name, 'name': name, 'original_email': person.email, 'email': email})
            if len(set(proposed_emails)) != len(proposed_emails) or session.exec(select(User.id).where(User.email.in_(proposed_emails))).first() is not None:
                raise RuntimeError('A proposed email conflicts with an existing account')
            vessels = session.exec(select(Spacecraft).where(Spacecraft.name.like('Salus Synthetic Vessel %')).order_by(Spacecraft.id)).all()
            if len(vessels) != 16:
                raise RuntimeError('The spacecraft set does not match the original cohort')
            for index, vessel in enumerate(vessels):
                name = f'{("Asteria", "Ícaro", "Ventura", "Arandu")[index % 4]} {index // 4 + 1:02d}'
                replacements[vessel.name] = name
                registry['spacecraft'].append({'id': vessel.id, 'original_name': vessel.name, 'name': name})
            replacements.update({f'Módulo Sintético {index + 1}': name for index, name in enumerate(('Módulo de Comando', 'Módulo de Habitação', 'Módulo de Pesquisa'))})
            ordered = sorted(replacements.items(), key=lambda row: len(row[0]), reverse=True)
            columns = connection.execute(text("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND data_type IN ('text','character varying','json','jsonb') ORDER BY table_name,ordinal_position")).all()
            inspector = inspect(connection)
            candidate = r'synthe|sint|fict|ficc|demo|simula|salus50-|Salus Synthetic'
            for table, column, data_type in columns:
                if table in ('knowledge_documents', 'knowledge_passages', 'alembic_version', 'revoked_tokens') or column in ('profile_id', 'rule_version', 'source', 'catalog', 'indicator', 'status', 'state', 'role', 'code', 'client_request_id', 'submission_hash', 'idempotency_key', 'input_fingerprint'):
                    continue
                keys = inspector.get_pk_constraint(table)['constrained_columns']
                if not keys:
                    continue
                selected = ', '.join(f'"{key}"' for key in keys)
                rows = connection.execute(text(f'SELECT {selected}, "{column}" AS value FROM public."{table}" WHERE "{column}"::text ~* :pattern'), {'pattern': candidate}).mappings().all()
                changed = 0
                batch = []
                for row in rows:
                    value = row['value']
                    updated = clean_value(value, ordered)
                    if table == 'spacecraft_modules' and column == 'technical_specifications' and isinstance(updated, dict):
                        updated.pop('dataset', None)
                    if updated != value:
                        batch.append({'new_value': updated, **{f'key_{key}': row[key] for key in keys}})
                        changed += 1
                if batch:
                    condition = ' AND '.join(f'"{key}" = :key_{key}' for key in keys)
                    statement = text(f'UPDATE public."{table}" SET "{column}" = :new_value WHERE {condition}')
                    if data_type in ('json', 'jsonb'):
                        statement = statement.bindparams(bindparam('new_value', type_=JSON))
                    connection.execute(statement, batch)
                    registry['changed_columns'].append({'table': table, 'column': column, 'rows': changed})
            session.expire_all()
            remaining = session.exec(select(Mission).where(Mission.id.in_(mission_ids))).all()
            if Counter(row.status for row in remaining) != {'completed': 35, 'in_progress': 10, 'planned': 5}:
                raise RuntimeError('Mission distribution changed unexpectedly')
            for row in registry['missions']:
                if session.get(Mission, row['id']).name != row['name']:
                    raise RuntimeError('A mission name was not updated')
            for row in registry['users']:
                if session.get(User, row['id']).name != row['name']:
                    raise RuntimeError('A crew name was not updated')
            session.commit()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'prepared', 'missions': len(registry['missions']), 'people': len(registry['users']),
                      'registry': str(registry_path), 'changed_columns': registry['changed_columns']}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Prepare plausible fictional labels and retain provenance outside the exported database')
    parser.add_argument('--manifest', default='data/synthetic_missions_public/manifest.json')
    parser.add_argument('--registry', default='data/synthetic_missions_public/presentation.json')
    prepare(parser.parse_args())


if __name__ == '__main__':
    main()
