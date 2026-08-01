# dashboard/Dockerfile — FakeCo "Real Appliances"
# Phase 33: multi-stage build — Node stage builds the Vite/React static bundle,
# then a python:3.12-slim runtime stage (matching every other custom service in
# this repo) serves it via FastAPI + the BFF's own API routes.

# --- Stage 1: build the frontend static bundle ---
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build
# vite.config.ts outputs to ../static, i.e. /app/static

# --- Stage 2: runtime (thin FastAPI BFF) ---
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY --from=frontend-build /app/static ./static

EXPOSE 8000

# No curl in this image (important.md #1) — healthcheck uses urllib instead.
HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
