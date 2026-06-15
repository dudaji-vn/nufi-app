## Introduction

### Purpose of this document
This document is the **functional specification** for the end-user–facing surfaces of the
**NuFi** platform: the **NuFi Chat** application (a customised fork of LibreChat) and the
**NuFi Console** (the self-service API-key and usage portal). It describes, feature by feature,
what each part of the product is expected to do, the user interface it presents, and the
acceptance criteria by which correct behaviour is judged.

The document exists because the project began without written specifications. It is intended to
become the single shared reference that the QA / testing function uses to understand the product,
design test cases, and decide whether a build behaves correctly.

### Audience
- **Primary:** QA engineers / testers who need to learn the product and verify its behaviour.
- **Secondary:** Product, support, and engineering staff who need an authoritative description of
  expected behaviour.

No prior knowledge of LibreChat is assumed. Where a behaviour is inherited from upstream
LibreChat, it is described from the end user's point of view rather than by reference to the
upstream project.

### Scope
**In scope** — the features that are *enabled in the NuFi deployment*:

- NuFi Chat: authentication & account access, chat core (compose / stream / edit / regenerate /
  fork), endpoint & model selection and conversation parameters, **Agents & File Search (RAG)**,
  per-message file upload, conversation management (sidebar, search, rename, delete, archive,
  bookmarks, share, export, multi-conversation, temporary chat), the Prompts library, and the
  account menu / settings (including the Console link).
- NuFi Console: authentication & just-in-time provisioning, the profile page, API-key lifecycle
  (list, create, reveal-once, revoke), and budget / usage display.

**Out of scope** — upstream LibreChat capabilities that are **not enabled** in the NuFi
configuration, including web search, the code interpreter, voice (TTS/STT), social/OAuth sign-in
via providers **other than Google** (GitHub, Discord, Facebook, Apple, OpenID, SAML — Google sign-in
**is** enabled and is in scope), and any endpoint other than the single custom **Nufi** endpoint
plus the **Agents** endpoint.
Where such a capability is visible in code but disabled by configuration, it is either omitted or
explicitly marked as *not enabled in NuFi*.

### How to read this specification
Each feature is documented with a consistent structure so it can be read and tested uniformly:

- **Purpose** — one sentence on what the feature is for.
- **Preconditions / access** — what must be true (configuration, authentication, prior state)
  before the feature is reachable.
- **UI elements** — the controls, fields, labels and icons the user sees. Real labels and, where
  useful, the underlying identifiers (translation keys, `data-testid`) are quoted so testers can
  locate elements precisely.
- **Functional behaviour** — numbered **FR-n** statements describing exactly what the system does.
- **States, edge cases, validation & errors** — empty states, failures, limits, and error
  messages.
- **Acceptance criteria** — numbered **AC-n** statements in *Given / When / Then* form. These are
  the testable conditions a build must satisfy.

> **Convention — "(verify: …)" markers.** Anywhere a detail could not be confirmed with certainty
> from the source code at the time of writing, it is annotated `(verify: …)`. These are deliberate
> flags for the tester to confirm against the running product, not assertions of fact. Treat every
> such marker as a small test task.

### Source of truth and versioning
The behaviour described here was derived from the NuFi source repositories:

- **NuFi Chat** — the LibreChat fork `dudaji-vn/nufichat`, release branch `fork/main`.
- **NuFi Console** — `dudaji-vn/nufi-console`, branch `develop`.
- **Deployment configuration** — the `nufi-chat` deployment wrapper (`librechat.yaml`,
  `docker-compose.yml`, `.env`), which determines exactly which features are enabled.

Because the product is under active development, this specification is a **living document**. When
behaviour changes, the relevant feature section and its acceptance criteria must be updated. Each
release should record which version of the product the document describes.

### References
- NuFi Chat deployment configuration: `librechat.yaml`, `.env.example` in the `nufi-chat` repo.
- LibreChat documentation (upstream behaviour reference): https://www.librechat.ai/docs
- NuFi Console architecture: `nufi-console/README.md`.
