# Build the box images on this machine (native arm64 on Apple Silicon) when CI is
# slow or the org has no arm runners. Requires `docker login ghcr.io`.
OWNER ?= dudaji-vn
TAG ?= main
PLATFORMS ?= linux/arm64
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)

# A LAN registry for boxes without GitHub access (a customer site, the Ubuntu
# VM test): `make registry-up` runs it on the Mac, `make registry-push
# REGISTRY=<mac-ip>:5000` retags and pushes the six NuFi images already built
# locally. CHAT_TAG/ADMIN_TAG default to the Mac's native arm64 dev builds;
# TAG/STUDIO_TAG default to the CI-built main images.
# REGISTRY_PORT is the host port `registry-up` publishes: the port in REGISTRY
# when it has one, else 5000. macOS holds 5000 itself (System Settings ->
# General -> AirDrop & Handoff -> AirPlay Receiver), so a Mac serving the images
# usually wants `REGISTRY=<mac-ip>:5001`.
REGISTRY ?= localhost:5000
REGISTRY_PORT ?= $(or $(word 2,$(subst :, ,$(REGISTRY))),5000)
CHAT_TAG ?= arm64-dev
ADMIN_TAG ?= arm64-dev
STUDIO_TAG ?= box-main

.PHONY: images test config registry-up registry-push
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

# Idempotent: a `registry:2` container already named nufi-registry is just
# started rather than re-created (docker run fails, `|| docker start` recovers).
# Re-running with a different REGISTRY_PORT therefore keeps the old port map —
# `docker rm -f nufi-registry` first if you move the port.
registry-up:
	docker run -d --name nufi-registry -p $(REGISTRY_PORT):5000 -v nufi-registry:/var/lib/registry registry:2.8.3 || docker start nufi-registry

# Retag+push each of the six NuFi images the box needs, from the ghcr.io/dudaji-vn
# tag already on this machine to $(REGISTRY). Explicit per-image lines (not a
# shell loop) so `make -n registry-push` shows all six tag/push pairs.
registry-push:
	docker tag ghcr.io/$(OWNER)/nufichat:$(CHAT_TAG) $(REGISTRY)/nufichat:$(CHAT_TAG) && docker push $(REGISTRY)/nufichat:$(CHAT_TAG)
	docker tag ghcr.io/$(OWNER)/nufichat-admin-panel:$(ADMIN_TAG) $(REGISTRY)/nufichat-admin-panel:$(ADMIN_TAG) && docker push $(REGISTRY)/nufichat-admin-panel:$(ADMIN_TAG)
	docker tag ghcr.io/$(OWNER)/nufi-console:$(TAG) $(REGISTRY)/nufi-console:$(TAG) && docker push $(REGISTRY)/nufi-console:$(TAG)
	docker tag ghcr.io/$(OWNER)/nufi-litellm:$(TAG) $(REGISTRY)/nufi-litellm:$(TAG) && docker push $(REGISTRY)/nufi-litellm:$(TAG)
	docker tag ghcr.io/$(OWNER)/nufi-ingest:$(TAG) $(REGISTRY)/nufi-ingest:$(TAG) && docker push $(REGISTRY)/nufi-ingest:$(TAG)
	docker tag ghcr.io/$(OWNER)/nufi-studio:$(STUDIO_TAG) $(REGISTRY)/nufi-studio:$(STUDIO_TAG) && docker push $(REGISTRY)/nufi-studio:$(STUDIO_TAG)
