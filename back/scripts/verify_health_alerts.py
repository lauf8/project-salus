import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]


def main():
    name = 'nasa_alerts_verify_' + uuid4().hex[:12]
    admin = psycopg.connect(host=os.environ['PGHOST'], port=os.environ['PGPORT'], user=os.environ['PGUSER'], password=os.environ['PGPASSWORD'], dbname='postgres', autocommit=True)
    environment = {**os.environ, 'PGDATABASE': name, 'PREFLIGHT_POSTGRES_TESTS': '1', 'ALERT_CONCURRENCY_TESTS': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    created = False
    try:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        created = True
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=environment, check=True)
        subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'], cwd=ROOT, env=environment, check=True)
    finally:
        if created:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        admin.close()


if __name__ == '__main__':
    main()
