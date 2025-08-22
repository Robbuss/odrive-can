FROM python:3.12-slim

WORKDIR /app

# Build deps for asyncpg/postgres
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Requirements
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Alembic + app code
COPY alembic.ini ./alembic.ini
COPY backend ./backend

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port 8000"]