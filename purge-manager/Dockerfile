FROM python:3.12-slim

# mysql client CLI used for Akaunting's ledger-truncate fallback (no native
# bulk-wipe API in Akaunting) — reuses the same "direct DB network access, no
# docker exec" pattern as snapshot-manager.
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
