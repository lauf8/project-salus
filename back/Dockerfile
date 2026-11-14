FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY agent_instructions.md ./agent_instructions.md
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY knowledge_seed.json ./knowledge_seed.json
COPY data ./data

EXPOSE 8000

CMD ["python", "-m", "scripts.startup", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
