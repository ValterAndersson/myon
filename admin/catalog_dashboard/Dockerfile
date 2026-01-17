FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# Set environment variables
ENV PORT=8080
ENV GOOGLE_CLOUD_PROJECT=myon-53d85
ENV CLOUD_RUN_REGION=europe-west1

# Run with gunicorn for production
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
