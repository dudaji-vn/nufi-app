#!/bin/bash
# First-boot provisioning on the shared Postgres: LiteLLM uses `nufi` (POSTGRES_DB),
# rag_api gets `nufi_rag`, NUFI Studio gets `nufi_studio`. pgvector is enabled
# where rag_api stores embeddings.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<-EOSQL
  CREATE DATABASE nufi_rag;
  CREATE DATABASE nufi_studio;
  GRANT ALL PRIVILEGES ON DATABASE nufi_rag TO ${POSTGRES_USER};
  GRANT ALL PRIVILEGES ON DATABASE nufi_studio TO ${POSTGRES_USER};
EOSQL
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname nufi_rag -c "CREATE EXTENSION IF NOT EXISTS vector;"
