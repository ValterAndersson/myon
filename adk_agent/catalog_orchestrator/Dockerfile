# Catalog Orchestrator Worker
# ============================
# Container for running catalog jobs as Cloud Run Jobs.
#
# Build:
#   docker build -t catalog-worker .
#
# Run locally:
#   docker run -e GOOGLE_APPLICATION_CREDENTIALS=/creds.json \
#              -v ~/.config/gcloud/application_default_credentials.json:/creds.json:ro \
#              catalog-worker
#
# In Cloud Run, auth uses the attached service account automatically.

FROM python:3.11-slim

# Prevent stdout buffering (important for Cloud Logging)
ENV PYTHONUNBUFFERED=1

# Don't write .pyc files
ENV PYTHONDONTWRITEBYTECODE=1

# Set PYTHONPATH so 'from app.xxx' imports work
ENV PYTHONPATH=/app

WORKDIR /app

# Install dependencies first (layer caching)
COPY agent_engine_requirements.txt .

# Install with explicit google-cloud packages needed by worker
RUN pip install --no-cache-dir -r agent_engine_requirements.txt \
    google-cloud-firestore \
    google-cloud-logging \
    google-auth

# Copy application code (order: least → most frequently changed)
COPY app/ app/
COPY workers/ workers/
COPY cli.py .

# Healthcheck (for local testing)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import app; print('ok')" || exit 1

# Default: run worker
# Override with: CMD ["python", "workers/catalog_worker.py", "watchdog"]
CMD ["python", "workers/catalog_worker.py"]
