# Single image, three entrypoints. The gateway, control plane and worker share
# all their code — separate images would mean three builds of the same tree and
# a class of bug where they drift apart on a shared contract.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a source change does not invalidate the pip layer.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[server]"

COPY shared/ ./shared/
COPY engines/ ./engines/
COPY services/ ./services/
COPY sdk/ ./sdk/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY examples/ ./examples/

ENV PYTHONPATH=/app:/app/sdk/python

# Run as a non-root user. This process sits in front of production traffic and
# has no reason to be able to write to its own image.
RUN useradd --create-home --uid 10001 custos && chown -R custos:custos /app
USER custos

EXPOSE 8000 8001

CMD ["uvicorn", "services.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
