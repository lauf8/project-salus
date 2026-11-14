from sqlmodel import Session, select

from app.database import engine
from app.data.exam_catalog import EXAMS, EXAM_TYPES
from app.models.preflight import ExamDefinition, ExamType
from app.schemas.exams import ExamCreate


def seed(session):
    types = {}
    for code, name in EXAM_TYPES:
        record = session.exec(select(ExamType).where(ExamType.code == code)).first()
        if record is None:
            record = ExamType(code=code, name=name, description='Catálogo baseado na referência NASA OCHMO-STD-100.1A, Rev. A.')
            session.add(record)
            session.flush()
        types[code] = record
    created = 0
    for item in EXAMS:
        if session.exec(select(ExamDefinition).where(ExamDefinition.code == item['code'])).first():
            continue
        payload = ExamCreate.model_validate({key: value for key, value in item.items() if key != 'category'} | {'exam_type_id': types[item['category']].id})
        session.add(ExamDefinition(**payload.model_dump(mode='json')))
        created += 1
    session.flush()
    return created


def main():
    with Session(engine) as session:
        count = seed(session)
        session.commit()
        print(f'Created {count} exam definitions. Existing definitions were preserved.')


if __name__ == '__main__':
    main()
