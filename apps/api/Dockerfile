FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

FROM base AS dependencies

COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml
RUN pip install --upgrade pip \
    && pip install -e "/app/apps/api"

FROM base AS dev

COPY --from=dependencies /app/apps/api/pyproject.toml /app/apps/api/pyproject.toml
RUN pip install --upgrade pip \
    && pip install -e "/app/apps/api[dev]"
COPY apps /app/apps
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini
EXPOSE 8000
CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS runtime

COPY --from=dependencies /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin
COPY apps /app/apps
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini
EXPOSE 8000
CMD ["uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
