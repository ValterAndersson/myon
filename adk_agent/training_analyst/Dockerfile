# Training Analyst Worker
# =======================
# Container for running training analysis jobs as Cloud Run Jobs.

FROM python:3.11-slim

# Prevent stdout buffering
ENV PYTHONUNBUFFERED=1

# Don't write .pyc files
ENV PYTHONDONTWRITEBYTECODE=1

# Set PYTHONPATH
ENV PYTHONPATH=/app

WORKDIR /app

# Install dependencies
COPY worker_requirements.txt .
RUN pip install --no-cache-dir -r worker_requirements.txt

# Copy application code
COPY app/ app/
COPY workers/ workers/

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "from workers.analyst_worker import AnalystWorker; print('ok')" || exit 1

# Default: run worker
CMD ["python", "workers/analyst_worker.py"]
