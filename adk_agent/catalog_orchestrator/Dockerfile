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

# Install worker-specific dependencies (NO google-adk)
COPY worker_requirements.txt .
RUN pip install --no-cache-dir -r worker_requirements.txt

# Copy application code (order: least → most frequently changed)
COPY app/ app/
COPY workers/ workers/
COPY cli.py .

# Healthcheck - verify worker module loads (not app.__init__ which is just a docstring)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "from workers.catalog_worker import CatalogWorker; print('ok')" || exit 1

# Default: run worker
# Override with: CMD ["python", "workers/catalog_worker.py", "watchdog"]
CMD ["python", "workers/catalog_worker.py"]
