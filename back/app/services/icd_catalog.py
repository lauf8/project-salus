import csv
import json
from functools import lru_cache
from hashlib import sha256
from io import StringIO
from pathlib import Path
from zipfile import ZipFile


CATALOG_PATH = Path(__file__).resolve().parents[2] / 'data' / 'icd10_who' / 'icd102019enMeta.zip'


@lru_cache(maxsize=1)
def icd_entries():
    metadata = json.loads(CATALOG_PATH.with_name('catalog.json').read_text())
    if sha256(CATALOG_PATH.read_bytes()).hexdigest() != metadata['sha256']:
        raise ValueError('WHO catalog checksum mismatch')
    with ZipFile(CATALOG_PATH) as archive:
        text = archive.read('icd102019syst_codes.txt').decode('utf-8-sig')
    entries = {}
    for row in csv.reader(StringIO(text), delimiter=';'):
        if len(row) >= 9:
            entries[row[6]] = {'code': row[6], 'name': row[8], 'selectable': row[1] == 'T'}
    return tuple(entries.values())


def icd_search(search='', page=1, per_page=50):
    query = search.casefold().strip()
    rows = [row for row in icd_entries() if query in row['code'].casefold() or query in row['name'].casefold()]
    return {'data': rows[(page - 1) * per_page:page * per_page], 'pagination': {
        'page': page, 'per_page': per_page, 'total': len(rows),
        'total_pages': (len(rows) + per_page - 1) // per_page,
        'has_next': page * per_page < len(rows), 'has_previous': page > 1,
    }, 'version': 'WHO ICD-10 2019, English', 'source_url': 'https://icdcdn.who.int/icd10/meta/icd102019enMeta.zip'}
