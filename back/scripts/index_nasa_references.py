import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from pypdf import PdfReader
from sqlmodel import Session, select

from app.database import engine
from app.models.knowledge import KnowledgePassage
from app.services.mission_rag import MissionRagService


DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / 'data' / 'nasa_references' / 'catalog.json'


def index_reference(session, service, entry, root, expected_dimension):
    filename = entry['file']
    if Path(filename).name != filename:
        raise ValueError('Reference paths must be filenames within the manifest directory')
    path = root / filename
    data = path.read_bytes()
    digest = sha256(data).hexdigest()
    if digest != entry['sha256']:
        raise ValueError(f'File checksum mismatch: {filename}')
    pages = len(PdfReader(path).pages)
    if pages != entry['page_count']:
        raise ValueError(f'Page count mismatch: {filename}')
    document = service.import_pdf(data, entry['title'], entry['source_url'], entry['revision'])
    if document['indexing_status'] != 'completed' or document['reindex_required'] or document['embedding_dimension'] != expected_dimension:
        document = service.process(document['id'])
    if document['indexing_status'] != 'completed':
        raise RuntimeError(document['indexing_error'] or 'Document indexing did not complete')
    passages = session.exec(select(KnowledgePassage).where(KnowledgePassage.document_id == document['id'], KnowledgePassage.embedding.is_not(None))).all()
    for passage in passages:
        if passage.section.startswith('pdf:'):
            passage.topic_codes = entry['topics']
            session.add(passage)
    session.commit()
    if not passages or any(len(passage.embedding) != expected_dimension for passage in passages):
        raise ValueError('The document index has missing or inconsistent vectors')
    results = service.search(entry['query'], document_id=document['id'], limit=2)
    if not results or not any(result['page'] is not None for result in results):
        raise ValueError('Page-aware vector retrieval did not return the imported reference')
    return {'document_id': document['id'], 'title': document['title'], 'file': filename,
            'sha256': digest, 'pages': pages, 'status': 'completed',
            'embedding_model': document['embedding_model'], 'embedding_dimension': expected_dimension,
            'embedded_passages': len(passages), 'retrieval_verified': True,
            'retrieval_examples': [{'passage_id': result['id'], 'page': result['page'], 'score': result['score']} for result in results]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    entries = json.loads(manifest.read_text(encoding='utf-8'))['documents']
    report_path = manifest.parent / 'index-report.json'
    report = {'verified_at': datetime.now(timezone.utc).isoformat(), 'documents': []}
    with Session(engine) as session:
        service = MissionRagService(session)
        capabilities = service.rag.capabilities()
        dimension = capabilities['embedding_dimension']
        for entry in entries:
            try:
                result = index_reference(session, service, entry, manifest.parent, dimension)
            except Exception as exc:
                session.rollback()
                result = {'file': entry['file'], 'status': 'failed', 'error': str(exc)[:600]}
            report['documents'].append(result)
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False), flush=True)
    failures = [row for row in report['documents'] if row['status'] != 'completed']
    if failures:
        raise SystemExit(f'{len(failures)} reference(s) failed; inspect {report_path}')
    print(json.dumps({'documents_completed': len(entries), 'total_pages': sum(row['pages'] for row in report['documents']),
                      'total_embedded_passages': sum(row['embedded_passages'] for row in report['documents'])}), flush=True)


if __name__ == '__main__':
    main()
