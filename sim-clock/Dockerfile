FROM python:3.12-slim

WORKDIR /app

# Real bug found during Phase 19 verification: docker-compose.yml's healthcheck for this
# service runs `curl -f http://localhost:8000/health`, but python:3.12-slim has no curl
# binary and this Dockerfile never installed one — the healthcheck silently fails forever
# ("exec: curl: executable file not found in $PATH"), which blocks any service that
# `depends_on: sim-clock: condition: service_healthy` (e.g. orchestrator) from starting at
# all in a clean/rebuilt environment.
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY main.py .

# Expose API port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
