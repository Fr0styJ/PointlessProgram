FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY migrate.py .
COPY migrations/ ./migrations/

# Runs once at startup and exits — used as an init container
CMD ["python", "migrate.py"]
