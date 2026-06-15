## Appendix A — Tester Quick-Start Guide

This appendix is a practical starting point for testing the NuFi product (NuFi Chat at
**https://chat.nufi.me**, NuFi Console at **https://console.nufi.me**). It does not replace the
feature sections; it tells you how to approach them.

### Get oriented first
1. Read **Introduction**, **Product Overview & Architecture**, and **Glossary** in full. The single
   most important concept to internalise is the difference between **Agent Knowledge** (persistent,
   retrievable, RAG) and a **per-message attachment** (conversation-scoped context). A large share
   of confusing bug reports come from mixing these up.
2. Skim every feature section once so you know the shape of the product before testing any part of
   it in depth.

### Set up your test accounts
- Create at least **two** end-user accounts so you can verify isolation (one user must never see
  another user's conversations, agents, files, keys, or usage).
- Keep one account "clean" (no conversations) to test empty states, and one "rich" (many
  conversations, agents, keys) to test lists, search, and pagination.

### Prepare test data
- **Documents for File Search / attachments:** at least one of each supported type — PDF, TXT, MD,
  CSV, DOCX, JSON — plus images (PNG, JPEG, WEBP, GIF). Prepare:
  - a small valid file of each type,
  - a file **just over 20 MB** (per-file limit),
  - a set of files that together exceed **50 MB** (total limit) and/or exceed **5 files** (count
    limit),
  - an **unsupported** type (e.g. `.zip`, `.exe`) to confirm rejection.
- **Knowledge content for RAG:** a document containing a unique, unguessable fact (e.g. a made-up
  policy number) so you can prove the model retrieved from it rather than from general knowledge.

### Recommended test order (by priority)
1. **Authentication & account access** — you cannot test anything else until sign-in works.
2. **Chat core** — sending, streaming, stop, regenerate, edit. The product's primary value.
3. **Endpoint / model / parameters** — confirm the Nufi endpoint and live model list.
4. **Agents & File Search (RAG)** — the flagship NuFi feature; budget the most time here.
5. **File upload & attachments** — limits and validation.
6. **Conversation management** — search, rename, delete, archive, bookmarks, share, export,
   multi-conversation, temporary chat.
7. **Prompts library.**
8. **Settings & Console link.**
9. **NuFi Console** — provisioning, profile, API-key lifecycle (especially reveal-once), budget &
   usage.

### How to use the acceptance criteria
Each **AC-n** is written in *Given / When / Then* form and is independently testable. Treat each AC
as the minimum bar. For thorough coverage, also test the **edge cases** listed in each section and
the negative paths (invalid input, oversize files, backend unreachable, expired session).

### Specifically verify the NuFi-only behaviours
- The welcome message reads **"Welcome to Nufi Chat."**
- Exactly two endpoints are offered: **Nufi** and **Agents** — nothing else.
- The account menu contains a **Console** entry that opens the NuFi Console **in a new tab**.
- File limits are **5 files / 20 MB each / 50 MB total** with exactly the supported types listed.
- RAG works **only** through an Agent with **File Search** — confirm there is no plain-chat RAG.
- A new Console API key's secret is shown **once** and cannot be retrieved afterwards.
- The features listed under *Known limitations / not-enabled features* are **absent**.

### Resolve every "(verify: …)" marker
Throughout this document, `(verify: …)` marks a detail that could not be confirmed from source
alone. Each is a small confirmation task against the running product. As you confirm them, the
document should be updated to remove the marker and state the confirmed behaviour.

### Reporting issues
When raising a defect, reference the relevant **feature section** and the specific **FR-n** or
**AC-n** that is violated, and include: environment/build, account used, exact steps, expected
result (quote the AC), actual result, and a screenshot or recording. Tying each report to an FR/AC
keeps defects unambiguous and makes regression testing repeatable.
