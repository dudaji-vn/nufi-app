---
name: smoke-test-litellm
description: Run a smoke test against the LiteLLM proxy to verify it is working
allowed-tools: Bash(curl *), Bash(docker compose *)
---

Verify the LiteLLM proxy is healthy:

1. Check the service is running: `docker compose ps litellm-proxy`
2. Liveness check: `curl -f http://localhost:4000/health/liveliness`
3. List models: `curl http://localhost:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"`
4. Test chat completion with a simple prompt
5. Verify the trace appears in Langfuse at http://localhost:3001

Report any failures with the full error message.
