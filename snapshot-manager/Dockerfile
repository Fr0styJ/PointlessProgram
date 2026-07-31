FROM python:3.12-slim

# pg_dump/pg_restore for the 5 Postgres-backed appliances (narrative, mattermost,
# zammad, wikijs, nextcloud) + mysqldump/mysql for the 2 MariaDB-backed appliances
# (wordpress, akaunting) + tar (present by default, kept explicit) for the
# mailserver Maildir and Nextcloud file-volume artifacts.
#
# IMPORTANT: every appliance Postgres instance in docker-compose.yml runs
# `postgres:16-alpine` — Debian bookworm's default `postgresql-client` meta-package
# pulls v17 client tools, and pg_restore's v17 client always emits
# `SET transaction_timeout = 0` (a GUC that only exists on PG17+ servers),
# which a v16 server rejects with "unrecognized configuration parameter" and
# aborts the restore. Discovered live during this phase's disposable-environment
# round-trip test. Fix: install the PGDG apt repo and pin postgresql-client-16
# explicitly so client and server major versions always match.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates wget gnupg lsb-release \
    && install -d /usr/share/postgresql-common/pgdg \
    && wget -q -O /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
       https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client-16 \
    default-mysql-client \
    tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000

# NOTE: healthcheck uses python's urllib, not curl — curl is not installed in any
# custom service image in this repo (see important.md gotcha #1).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
