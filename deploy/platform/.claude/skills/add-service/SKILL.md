---
name: add-service
description: Add a new service to docker-compose.yml following NPUOps conventions
allowed-tools: Read, Edit, Bash(docker compose config)
---

When adding a new service to docker-compose.yml:

1. Pin the image version (NEVER use `:latest`)
2. Add a healthcheck section
3. Define explicit network membership
4. Set `restart: unless-stopped`
5. Add environment variables to `.env.example` (with placeholders)
6. Mount volumes for persistent data
7. Add `depends_on` with `service_healthy` condition where applicable
8. Run `docker compose config` to validate after editing

Template:

```yaml
service-name:
  image: provider/image:v1.2.3
  restart: unless-stopped
  environment:
    - VAR=${VAR}
  volumes:
    - ./service-name-data:/data
  networks:
    - npuops-net
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:PORT/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

After adding, update `.env.example` with all required vars.
