#!/bin/bash
# First-boot provisioning on the shared Postgres: LiteLLM uses `nufi` (POSTGRES_DB),
# rag_api gets `nufi_rag`, NUFI Studio gets `nufi_studio`. NUFI Works gets
# nufi_works. pgvector is enabled where rag_api stores embeddings.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<-EOSQL
  CREATE DATABASE nufi_rag;
  CREATE DATABASE nufi_studio;
  CREATE DATABASE nufi_works;
  GRANT ALL PRIVILEGES ON DATABASE nufi_rag TO ${POSTGRES_USER};
  GRANT ALL PRIVILEGES ON DATABASE nufi_studio TO ${POSTGRES_USER};
  GRANT ALL PRIVILEGES ON DATABASE nufi_works TO ${POSTGRES_USER};
EOSQL
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname nufi_rag -c "CREATE EXTENSION IF NOT EXISTS vector;"
