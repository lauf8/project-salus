import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]


def main():
    name = 'nasa_alerts_verify_exams_' + uuid4().hex[:12]
    credentials = dict(host=os.environ['PGHOST'], port=os.environ['PGPORT'], user=os.environ['PGUSER'], password=os.environ['PGPASSWORD'])
    environment = {**os.environ, 'PGDATABASE': name, 'PREFLIGHT_POSTGRES_TESTS': '1', 'ALERT_CONCURRENCY_TESTS': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    admin = psycopg.connect(**credentials, dbname='postgres', autocommit=True)
    created = False

    def migrate(direction, revision):
        subprocess.run([sys.executable, '-m', 'alembic', direction, revision], cwd=ROOT, env=environment, check=True)

    try:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        created = True
        migrate('upgrade', 'e26d7f8091a2')
        with psycopg.connect(**credentials, dbname=name) as connection:
            user_id = connection.execute("INSERT INTO users (name, email, hashed_password, is_astronaut, is_physician, allergy_screening_completed) VALUES ('Legacy astronaut', 'legacy@migration.test', 'test', true, false, false) RETURNING id").fetchone()[0]
            mission_id = connection.execute("INSERT INTO missions (name, planned_launch_at) VALUES ('Migration verification', now()) RETURNING id").fetchone()[0]
            member_id = connection.execute("INSERT INTO mission_members (mission_id, user_id, role) VALUES (%s, %s, 'astronaut') RETURNING id", (mission_id, user_id)).fetchone()[0]
            type_id = connection.execute("INSERT INTO exam_types (code, name, is_active) VALUES ('legacy_migration', 'Legacy type', true) RETURNING id").fetchone()[0]
            requirement_id = connection.execute('INSERT INTO mission_exam_requirements (mission_id, exam_type_id, is_required, due_days_before_launch) VALUES (%s, %s, true, 10) RETURNING id', (mission_id, type_id)).fetchone()[0]
            exam_id = connection.execute('INSERT INTO astronaut_exams (mission_id, mission_member_id, requirement_id, due_at) VALUES (%s, %s, %s, now()) RETURNING id', (mission_id, member_id, requirement_id)).fetchone()[0]
            result_id = connection.execute("INSERT INTO exam_results (astronaut_exam_id, performed_at, recorded_at, recorded_by_user_id, summary) VALUES (%s, now(), now(), %s, 'Preserved legacy result') RETURNING id", (exam_id, user_id)).fetchone()[0]
        migrate('upgrade', 'head')
        with psycopg.connect(**credentials, dbname=name) as connection:
            row = connection.execute('SELECT summary, structured_values, reference_ranges, exam_snapshot FROM exam_results WHERE id = %s', (result_id,)).fetchone()
            assert row == ('Preserved legacy result', {}, {}, None), row
            assert connection.execute('SELECT definition_snapshot FROM astronaut_exams WHERE id = %s', (exam_id,)).fetchone()[0] is None
        migrate('downgrade', 'e26d7f8091a2')
        with psycopg.connect(**credentials, dbname=name) as connection:
            assert connection.execute('SELECT summary FROM exam_results WHERE id = %s', (result_id,)).fetchone()[0] == 'Preserved legacy result'
        migrate('upgrade', 'head')
        print('Migration upgrade/downgrade preserved existing results.', flush=True)
        subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'], cwd=ROOT, env=environment, check=True)
    finally:
        if created:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        admin.close()


if __name__ == '__main__':
    main()
