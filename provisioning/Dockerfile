FROM python:3.12-slim

WORKDIR /app

# Need docker CLI inside to exec into mailserver container.
# NOTE: on this base image's Debian release, `docker.io` only ships the daemon (dockerd) —
# the actual client binary is in the separate `docker-cli` package. `docker.io` alone silently
# leaves /usr/bin/docker missing (apt succeeds since docker.io is a real, installable package;
# it just isn't the CLI), so every provisioning run failed with
# "[Errno 2] No such file or directory: 'docker'" until this was traced down.
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker-cli \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY provisioning/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY provisioning/main.py .
COPY personality-library/ ./personality-library/

# Default: provision all active employees
# Override CMD to provision-principal or fire a specific employee
CMD ["python", "main.py", "provision", "--all"]
