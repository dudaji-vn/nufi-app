# Build the box images on this machine (native arm64 on Apple Silicon) when CI is
# slow or the org has no arm runners. Requires `docker login ghcr.io`.
OWNER ?= dudaji-vn
TAG ?= main
PLATFORMS ?= linux/arm64
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)

.PHONY: images test config
images:
	docker buildx build --platform $(PLATFORMS) --push -t ghcr.io/$(OWNER)/nufi-litellm:$(TAG) $(ROOT)/deploy/platform/litellm
	docker buildx build --platform $(PLATFORMS) --push -t ghcr.io/$(OWNER)/nufi-ingest:$(TAG) $(ROOT)/deploy/platform/adapters/nufi-ingest
	docker buildx build --platform $(PLATFORMS) --push --build-arg VITE_NUFI_ENTER_URL=/nufi/enter/studio \
	  -t ghcr.io/$(OWNER)/nufi-studio:box-$(TAG) -f $(ROOT)/apps/nufi-agent/nufi/Dockerfile $(ROOT)/apps/nufi-agent
	docker buildx build --platform $(PLATFORMS) --push -t ghcr.io/$(OWNER)/nufichat:$(TAG) -f $(ROOT)/apps/chat/Dockerfile $(ROOT)/apps/chat
	docker buildx build --platform $(PLATFORMS) --push -t ghcr.io/$(OWNER)/nufi-console:$(TAG) $(ROOT)/apps/console
	docker buildx build --platform $(PLATFORMS) --push -t ghcr.io/$(OWNER)/nufichat-admin-panel:$(TAG) $(ROOT)/apps/admin-panel
test:
	python3 -m pytest tests -q
config:
	docker compose config >/dev/null && echo "compose ok"
