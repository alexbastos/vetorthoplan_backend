FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
RUN pip install . \
    && useradd --system --uid 10001 --create-home vetorthoplan

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "vetorthoplan.bootstrap:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
