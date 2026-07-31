FROM python:3.12-slim

WORKDIR /app

# Phase 19: needs the docker CLI to `docker exec fakeco-mailserver doveadm sieve ...` for
# PTO vacation-responder scripts. Must be `docker-cli`, not `docker.io` — see
# provisioning/Dockerfile's comment (this session already hit + fixed that exact bug once).
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker-cli \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
