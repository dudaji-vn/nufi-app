#!/bin/bash
# Provisions a separate `langfuse` database on the shared Postgres instance.
# Runs once on first volume init (Postgres entrypoint convention).
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" <<-EOSQL
  CREATE DATABASE langfuse;
  GRANT ALL PRIVILEGES ON DATABASE langfuse TO ${POSTGRES_USER};
EOSQL
