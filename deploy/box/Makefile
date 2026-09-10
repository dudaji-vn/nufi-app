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
# REGISTRY is the address the *box* pulls from (`<mac-ip>:5001`), which has no
# certificate. Docker refuses a plain-HTTP push unless the daemon is told the
# registry is insecure — and on Docker Desktop that means editing Settings and
# restarting the engine. Loopback is the exception every Docker trusts out of
# the box, so this machine pushes to `localhost:<same port>`: the same registry
# container, the same stored images, no daemon change. Override PUSH_REGISTRY
# to push to a registry that is somewhere else.
PUSH_REGISTRY ?= localhost:$(REGISTRY_PORT)
# Two third-party images live on ghcr.io as well, so a box that cannot reach
# GitHub cannot pull them either — mirror them next to the NuFi six. Pinned by
# digest / exact release here; served from the mirror under $(TAG).
RAG_IMAGE ?= ghcr.io/danny-avila/librechat-rag-api-dev-lite@sha256:f9f34c8ed6884b0ff9b17387e6174fed737dba29f21622ecb75604d82bc47bf8
SAMBA_IMAGE ?= ghcr.io/servercontainers/samba:a3.24.1-s4.23.8-r0
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
# tag already on this machine to $(PUSH_REGISTRY). Explicit per-image lines (not
# a shell loop) so `make -n registry-push` shows all six tag/push pairs.
#
# The tag changes on the way in: what a box pulls is ${NUFI_*_TAG} from its own
# .env, which install-box.sh writes as `main` (and `box-main` for studio). The
# copy on this machine may be tagged anything — a native arm64 build is
# `arm64-dev` — so the source tag is a variable and the destination is the tag
# the box will ask for. Pushing the source tag instead is what made the first
# blank-VM install die with `nufichat-admin-panel:main: not found`.
registry-push:
	docker tag ghcr.io/$(OWNER)/nufichat:$(CHAT_TAG) $(PUSH_REGISTRY)/nufichat:$(TAG) && docker push $(PUSH_REGISTRY)/nufichat:$(TAG)
	docker tag ghcr.io/$(OWNER)/nufichat-admin-panel:$(ADMIN_TAG) $(PUSH_REGISTRY)/nufichat-admin-panel:$(TAG) && docker push $(PUSH_REGISTRY)/nufichat-admin-panel:$(TAG)
	docker tag ghcr.io/$(OWNER)/nufi-console:$(TAG) $(PUSH_REGISTRY)/nufi-console:$(TAG) && docker push $(PUSH_REGISTRY)/nufi-console:$(TAG)
	docker tag ghcr.io/$(OWNER)/nufi-litellm:$(TAG) $(PUSH_REGISTRY)/nufi-litellm:$(TAG) && docker push $(PUSH_REGISTRY)/nufi-litellm:$(TAG)
	docker tag ghcr.io/$(OWNER)/nufi-ingest:$(TAG) $(PUSH_REGISTRY)/nufi-ingest:$(TAG) && docker push $(PUSH_REGISTRY)/nufi-ingest:$(TAG)
	docker tag ghcr.io/$(OWNER)/nufi-studio:$(STUDIO_TAG) $(PUSH_REGISTRY)/nufi-studio:box-$(TAG) && docker push $(PUSH_REGISTRY)/nufi-studio:box-$(TAG)
	docker pull -q $(RAG_IMAGE) && docker tag $(RAG_IMAGE) $(PUSH_REGISTRY)/librechat-rag-api-dev-lite:$(TAG) && docker push $(PUSH_REGISTRY)/librechat-rag-api-dev-lite:$(TAG)
	docker pull -q $(SAMBA_IMAGE) && docker tag $(SAMBA_IMAGE) $(PUSH_REGISTRY)/samba:$(TAG) && docker push $(PUSH_REGISTRY)/samba:$(TAG)
