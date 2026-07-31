FROM python:3.12-slim

WORKDIR /app

# Need docker CLI inside to exec into mailserver container
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker.io \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Default: provision all active employees
# Override CMD to provision-principal or fire a specific employee
CMD ["python", "main.py", "provision", "--all"]
