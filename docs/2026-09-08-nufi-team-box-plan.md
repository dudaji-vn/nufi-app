# NuFi appliance — a box a basic developer can install in one command

2026-09-08 · status: draft for review · revision 3 (self-contained in nufi-app; install bar = one command for a basic developer)

## 0. The ask, in the requester's words

| Requester's words | What answers it | State today | What is missing |
|---|---|---|---|
| "install the NuFi appliance on a spare laptop (or PC)" | one command on a fresh Ubuntu, four questions, a URL (§2) | `deploy/platform` runs on a dev machine from a git checkout and a terminal | An installer a basic developer can run without reading the repo; images published instead of built; an inference profile for a PC |
| "try out RAG, chat, agents" | the NuFi app + rag_api + NUFI Studio, all on the box | Chat and gateway run in `deploy/platform`; rag_api and Studio run elsewhere (Railway) | rag_api and Studio in the box compose; RAG scoped per department; a routine with an input; a scheduler |
| "access it from outside without needing a static IP" | Headscale coordinator with embedded DERP relay, run by Dudaji; `tailscale` on the box and on laptops | Nothing in nufi-app; lab-proven in the appliance repo | The coordinator service; the box as a mesh node; one-click join file for laptops |
| "a shared drive, a chat tool, and an AI agent" for Legal, HR, General Affairs, Strategy | Samba on the box bound to the mesh; the app; Studio routines; a watcher that turns dropped files into knowledge | Nothing for the drive in nufi-app | Samba service, drive pages in the admin panel, `nufi-ingest`; the four department weeks in §6 |
| "check this file" (`NuFi_Team_Product_Intro_EN.html`) | §7 | — | One claim ("Email — included") is not built |
| "hardware good enough, install easily, use right away" · "If you buy our PC" | a short hardware list (§8) and install level 1 done well (§2); level 3 when we sell the PC | — | The SKU list; the installer and `nufi-box` command; updates and remote support |

**Decision behind this revision:** the box ships from **this repo**, self-contained, as `deploy/box/`. The appliance repo (`dudaji/appliance`) is a reference, not a dependency. What we take from it as ideas: the honest boundary (409 unwired, 502 upstream failure, never a fabricated answer), zero secrets in the shipped image, naming the box on the mesh so a drive is `\\nufi\legal`, the one-click join file, tiers by footprint, and the department recipes. What we do not rebuild: its portal, catalog, leads, i18n, and the custom WireGuard connector it has itself retired in favour of Headscale.

## 1. Target picture

```
   laptop (home / LTE / branch)                        mesh.nufi.me  (Dudaji-run)
   Tailscale app + one file from the box   ──────────▶ headscale + DERP relay
              │  WireGuard end to end; the relay sees only ciphertext
   ┌──────────┼───────────────────────────────────────────────────────────────┐
   │  the box ▼  Ubuntu 24.04 + one command · no inbound ports                │
   │  tailscale (node "nufi")   avahi nufi.local   caddy (box CA)             │
   │  smbd on the mesh IP  →  \\nufi\legal  \\nufi\hr  \\nufi\strategy …      │
   │                                                                          │
   │  https://nufi:3080 :3001 :3002 :7860 (one hostname, one CA, ports)       │
   │      │                 │                                                 │
   │  litellm :4000 ────────┘        rag_api :8000 ── pgvector                │
   │      │                               ▲                                   │
   │  ollama :11434 (GPU)            nufi-ingest ── watches /srv/drives/*     │
   │  qwen2.5:7b · bge-m3                                                     │
   │  nufi-updater (nightly, signed bundle, rollback)                         │
   └──────────────────────────────────────────────────────────────────────────┘
```

Decisions in the picture:

- **Members use the NuFi app UI** (`chat.nufi.mesh`). It already has agents, file search, teams and the console SSO into Studio. There is no second "lite" AI surface to maintain.
- **NUFI Studio is the on-box agent. NUFI Works stays in the cloud.** Works needs a Kubernetes cluster with gVisor and Cilium (`docs/2026-09-03-works-sandbox-cluster-decision.md`); a PC cannot honour that.
- **Dudaji runs one coordinator for every box.** NAT traversal needs one publicly reachable host; that is physics, not a design choice. Running it ourselves is what keeps the customer at zero monthly cost, zero router work and zero static IP. The relay carries ciphertext only. An enterprise that insists can self-host the same compose file; that is a documented option, not the default.
- **Linux x86 with an NVIDIA GPU is the only box we sell in v1. An Apple Silicon Mac is a supported demo and dev host.** Docker on macOS cannot reach the GPU, so Ollama runs natively on Metal (the stack already points at `host.docker.internal:11434`), the drive is macOS File Sharing rather than a Samba container, and the installer has a Homebrew branch. It is the machine the first demos are filmed on; it is not a SKU.

## 2. Three install levels, and which one we commit to

| Level | Customer does | Who can do it | Real-world peer |
|---|---|---|---|
| 1 · one command | installs Ubuntu 24.04, runs one command, answers four questions, opens the URL it prints | a basic developer or the customer's IT person | Coolify, Docker, Tailscale installers |
| 2 · USB image + wizard | plugs in a USB stick, boots once, opens `http://nufi.local`, answers the same four questions | an office worker | Home Assistant OS, TrueNAS |
| 3 · pre-installed | plugs in power and LAN, opens the URL on the sticker | anyone | Synology; "If you buy our PC" |

**We commit to level 1, done as well as Coolify does it.** The person installing is a basic developer or the customer's IT staff, with the guide open next to them. Level 3 is level 1 performed at our desk before the PC ships, so it costs nothing once level 1 is solid. Level 2 is deliberately later: it is four to six weeks of image pipeline and wizard, and it only pays off when customers bring their own hardware in numbers.

**What "one command" means, exactly:**

```bash
# fresh Ubuntu 24.04, wired network, optional NVIDIA GPU
curl -fsSL https://get.nufi.me/box | bash
```

The script installs Docker, the NVIDIA container toolkit when a GPU is present, and `tailscale`; pulls the box images; asks four questions (box name, admin email, departments to create as drives, inference profile with a default chosen from the detected GPU and RAM); generates every secret on the box; starts the stack; and prints `http://<box-ip>:3080` with the admin login. Fifteen minutes on the office network, most of it downloads. Re-running is safe and keeps the answers.

It leaves behind one command, `nufi-box`, with the verbs a non-expert needs and no others:

| Verb | Does |
|---|---|
| `status` | every service, the model loaded, disk, last backup, mesh state |
| `invite <name>` | issues a laptop join file (§3 H) |
| `drive add <name>` | creates a share and its RAG scope |
| `update` | pulls the next signed bundle, applies it, rolls back on a failed health check |
| `backup` / `restore` | to the `backup` share or a USB disk |
| `support on` / `support off` | lets Dudaji join the box's mesh, logged |
| `doctor` | prints what is wrong in words a ticket can quote |

**Operating systems the installer supports**, all through the same script and the same four questions:

| Host OS | Container runtime | Inference | Drive | Notes |
|---|---|---|---|---|
| Ubuntu / Debian | Docker Engine (apt) | Ollama container with NVIDIA toolkit, or native | Samba container | the sold SKU |
| Fedora / RHEL family | Docker Engine (dnf) | same | same | best effort, tested once per release |
| macOS (Apple Silicon or Intel) | OrbStack or Docker Desktop (Homebrew) | Ollama native on Metal | macOS File Sharing | demo and dev host |
| Windows 10/11 | Docker Desktop with WSL2; the script runs inside WSL Ubuntu | Ollama native on Windows (CUDA) | Windows File Sharing | dev host; the guide covers the WSL step |

Every image is published for `linux/amd64` and `linux/arm64`, so an ARM host is never emulated.

**On the laptop side** the member installs the official Tailscale app and double-clicks the file from `invite`; it logs in to our coordinator and maps the drives. On Windows this needs local admin rights; a company laptop locked by IT is a real blocker and the guide says so up front.

## 3. What blocks a blank PC, and the fix for each

| # | Gap | Fix | Phase |
|---|---|---|---|
| A | litellm, scanner, adapters are `build:` from source; app and console images are amd64 only | CI publishes `nufi-litellm`, `nufi-scanner`, `nufi-ingest` to GHCR on push to `main` and on a `nufi-box-v*` tag, and every box image is built for `linux/amd64` **and** `linux/arm64` (today an Apple Silicon host runs the app under emulation, see `deploy/platform/docker-compose.override.yml`) | P1 |
| B | GHCR images are private; a customer box has no GitHub login | Dogfood: a read-only `read:packages` token in the installer. Product: the installer downloads a signed offline bundle from `updates.nufi.me`, the same bundle `nufi-box update` uses; no registry login on a customer box, ever | P1 / P4 |
| C | No inference profile for a PC | `INFERENCE_PROFILE=ollama` (default: `qwen2.5:7b-instruct` chat, `bge-m3` embeddings, both Apache/MIT) · `remote` (vLLM or RNGD on the LAN) · `cloud` (dev only, breaks the air gap, egress guard stays in `audit`) | P1 |
| D | rag_api and Studio are not in the on-prem compose | `deploy/box/docker-compose.yml`: the `box` tier = app, litellm, pgvector, mongodb, rag_api, ollama, studio, console, admin-panel, samba, nufi-ingest, caddy, tailscale (13). `standard` adds Langfuse; `full` adds the detectors and monitoring, layered with `-f` as today | P1 |
| E | RAG has no scope: every question competes with every document | The app already isolates agent Knowledge per team; the drive watcher ingests with `entity_id = drive id`, and the app maps a department team to its drive. The daemon runs as the admin and shares each agent to its department team, so the admin owns and can invite members into every department. No portal contract to change any more | P1 |
| F | A file dropped in `\\nufi\legal` is not knowledge | `nufi-ingest`: stdlib watcher over `/srv/drives/<id>/`, read-only mount; new or changed file → rag_api `POST /embed` with `file_id` and `entity_id`; deleted → `DELETE /documents`. rag_api parses PDF, DOCX, XLSX, text | P1 |
| G | Routines have no input | A Studio flow takes `input_value` and a drive path; the app's agent run passes both. Scheduled routines are a small `nufi-cron` sidecar (crontab in a config file, calls Studio's run API), no new UI beyond a schedule field on the flow | P2 / P3 |
| H | No mesh in nufi-app | `deploy/coordinator/`: headscale with embedded DERP behind Caddy, on one VPS as `mesh.nufi.me`. On the box: `tailscale` as a service, joined by the installer with a key it requests from the coordinator | P2 |
| I | No drive in nufi-app | `samba` service bound to the mesh IP only (`interfaces`, `bind interfaces only`), shares rendered from the admin panel's drive list; `avahi` announces `nufi.local` on the LAN, MagicDNS answers `nufi` on the mesh | P2 |
| J | No laptop or drive management UI | Two pages in the admin panel, "Network" (nodes, invite, revoke; calls the headscale API) and "Drives" (create, quota, who may read); writing `smb.conf` and reloading is a small privileged helper on the box | P2 |
| K | `.mesh` cannot carry an SSO cookie | one hostname, four ports; cookies ignore ports; `IDENTITY_COOKIE_DOMAIN=` empty; TLS from P1 because both apps set Secure cookies and Studio requires https for JWKS | P1 |
| L | Box CA must be trusted on laptops | The join file installs the box root cert; the invite page also offers it alone. Plain HTTP inside the tunnel was considered and rejected: the app sets `Secure` cookies in production | P1 |
| M | No installer | `install-box.sh` served as `get.nufi.me/box`: prerequisites, pull, four questions, secrets, up, URL; idempotent | P1 |
| N | No day-two command | `nufi-box` (§2): status, invite, drive add, update, backup, restore, support, doctor | P2 / P4 |
| O | No update path | `nufi-box update`: signed bundle from `updates.nufi.me`, health-checked apply, rollback; optional nightly timer; a USB path for offline sites | P4 |
| P | No backup | Nightly `pg_dumpall` and `mongodump` into a `backup` share, and optionally to an external USB disk; restore is documented and tested once per release | P3 |
| R | The first demo host is a Mac | `install-box.sh` Darwin branch: OrbStack or Docker Desktop, `ollama` via Homebrew, drives as macOS File Sharing folders, sleep disabled on power; everything else identical to Ubuntu | P1 |
| Q | Hardware is unbounded | A short recommended list (§8); the installer warns below the minimum and says which line failed, and refuses without wired Ethernet or 32 GB RAM | P4 |

Licence notes: MongoDB's SSPL binds hosting as a service, not shipping inside a sold appliance, so it is acceptable here but still blocks any hosted tier. MinIO only enters at standard tier through Langfuse; swap to SeaweedFS before a standard-tier sale. Redis → Valkey is a one-line change. Do not use EXAONE for Korean despite its quality: its licence is non-commercial.

## 4. Phases

Dates start today. Each phase ends with a weekly demo video in the established format, filmed on the real box.

### P0 · Alignment · Sep 8–10

- Send this plan and the claim table (§7) to the board, with the two decisions stated plainly: the box ships from nufi-app, and Dudaji runs the coordinator.
- Ask for one VPS (1 vCPU, 1 GB, a DNS name, ports 443 and 3478) and one box for dogfood: a small-form-factor PC, 64 GB RAM, one 24 GB NVIDIA GPU, Ubuntu 24.04.

### P1 · The box on the LAN · Sep 11–24

Goal: a colleague on the office LAN, with no engineer present, does the Legal week in a browser.

- Images published (A); `deploy/box/` compose with rag_api, Studio, ollama, samba, `nufi-ingest` (C, D, F); `install-box.sh` (M); team ↔ drive scoping (E).
- Acceptance, scripted as `scenarios/run.py --box`: first on Sun's Mac (the demo), then a developer outside the team installs from a blank Ubuntu with only the guide, in under 30 minutes on the office network; drops three Legal PDFs into the share; within a minute a question in chat returns an answer with sources from those files only; a Studio flow runs from the app. Measured on Sun's Mac 2026-09-08: install 75 s, ingest 32–97 s cold, 10/32 on qwen2.5:7b at temperature 0 with 0/32 answers differing across two runs — the mechanism holds and reproduces; the score is the model's.

### P2 · From home · Sep 25–Oct 15

Goal: from an LTE hotspot, a laptop joins, opens `chat.nufi.mesh`, asks about a file it just dropped, and runs a routine with an input.

- Coordinator on the VPS (H); box as a mesh node; samba on the mesh IP and `nufi.local` (I); admin-panel Network and Drives pages (J); aliases, cookie domain, CA (K, L); routine input (G); the first four recipe flows shipped as JSON (team document Q&A, meeting summary from a pasted transcript, internal helpdesk, weekly report from a department drive).
- Acceptance: the four-step "day at home" from §6 recorded end to end, including the case where NAT forces the DERP relay. Scripted as `deploy/coordinator/lab/day-at-home.sh`: the member is a container behind a NAT that forwards no UDP but STUN, the box is a real install in a Lima VM. Measured 2026-09-09, relay forced, **all 8 checks pass**:

  | check | result |
  |---|---|
  | box-on-mesh | PASS — but the check asked only whether headscale *lists* a node called `nufi`, and the lab keeps its registrations between runs, so this row could not have said otherwise either; 38 s from cold in the previous run |
  | path | PASS (DERP) — every packet relayed |
  | health-over-mesh | PASS — `https://nufi.box.lab:3080/health` 200 through MagicDNS, on the box's own CA |
  | login-over-mesh | PASS — the chat app took the member's credentials |
  | drive-write | PASS — but on a probe file the box already held, so this row could not have said otherwise; the write itself is proven by the previous run and by the live `put` that closed D1 |
  | drive-ingested | PASS — the file was already embedded on this box; the fresh measurement is the previous run's 31 s |
  | agent-cites-drive | PASS — the Legal agent cited `contract.txt` and `계약검토_표준조항.txt` |
  | routine-weekly | PASS — `weekly ok 7s` over the mesh |

  `relay forced | lab up 8 s | box up + joined 5 s | agent 513 s | routine 10 s | total 548 s`. One number and three rows are the harness's and not the box's: the VM was already running when this run started, so the 5 s is `mesh up` alone and the cold figure is the previous run's 38 s; `box-on-mesh` gated on headscale *listing* the node, and the lab keeps its volumes on purpose so that list holds every box that ever joined; `drive-write` gated on a fixed probe file the box already held, with `smbclient`'s exit status discarded, so a refused write would have read PASS too; and `drive-ingested` matched a line the previous run had written, because `nufi-ingest`'s container log survives a restart and the check greps all of it — the honest ingest figure is that run's 31 s, on the file's first embedding. All three are now fixed in the harness — a new probe file with new contents every run, `drive-write` gating on `smbclient`'s status as well, and `box-on-mesh` gating on the node being `online` — so run 4 will be the first table where every row is its own measurement. The agent's 513 s is a cold `qwen2.5:0.5b`; 1 of 4 judge verdicts passed, which is the model's score and not the box's, and the check's gate is that an answer carried a citation at all — two did.

  **Eight of eight**, and the script exits 0 only when every row passes — which is what the harness asserted, not eight independent measurements: five of the rows are trustworthy and the three above are not. That the box really was on the mesh is not in doubt — `path`, `health-over-mesh` and `login-over-mesh` are live and all three passed — but that is corroboration from other rows, which is the same thing being refused for `drive-write`, so `box-on-mesh` is counted the same way. This is the third end-to-end run: the first, before any fix, passed 5 of 8 and found three defects; the second passed 7 of 8 and found a fourth. Three of the four are fixed, and each is closed on the real box through the whole harness rather than on a proxy; the fourth is disclosed rather than fixed:

  - **A member could not write to a department drive** — `NT_STATUS_ACCESS_DENIED`; `docker-compose.linux.yml` pinned the Samba account to uid 1000 while the installer created the drives as whoever ran it. Fixed; `drive-write` and `drive-ingested` have passed live ever since.
  - **An upgraded mesh box lost its whole front door** — a generated `caddy/mesh.caddy` its new Caddyfile could no longer read, crash-looping Caddy on every port. Fixed; the box has come up clean on both runs since.
  - **A re-install left the box unable to call its own routines** — `install-box.sh` rewrote `.env` without `STUDIO_API_KEY`, which is minted afterwards by `nufi-box flows install` and never asked for as an answer, so a box whose Studio was slow at that step kept its routines and lost the key. Fixed: the key is now rendered back like every other secret in the file, deliberately *not* as a command-line override, because it is a bearer token for the whole of Studio. This box needed the documented one-command repair (`nufi-box flows install`) before the run, since the fix prevents the loss rather than undoing one.
  - **Nothing caps how much a routine generates, or stops a run whose caller has gone** — still disclosed rather than fixed, because the cap belongs on the routine's model node and this Studio build's Ollama component does not expose it. The fix is in `apps/nufi-agent`, not here, and it is P3 work.

  On that last one this run is worth reading carefully, because it says two things at once. `routine-weekly` **passed in 7 s**, so the limitation does not bite `weekly` on `qwen2.5:0.5b` — the first time that row has been measured in either direction. And in the same run one of the four Legal questions ran away in front of us: ollama's log shows `n_gen` past **40,000 tokens** with `slot context shift, n_keep = 4, n_discard = 2045`. It stopped on its own, at roughly 490 s of generation, and the run carried on. Nothing in the *harness* would have stopped it — `run_box.py`'s stream timeout is a read timeout, and a stream that keeps arriving never trips it — but the gateway would have: chat and agents reach the model through LiteLLM, whose `request_timeout: 600` is the backstop the box README already claims for them, and 40,242 tokens at the logged 82 t/s fits inside that window. What has no backstop at all is the routine path, which talks to Ollama directly and bypasses the gateway. So the limitation is exactly as disclosed, and what this run adds is that the same runaway shows up in chat as a very slow question rather than an unbounded one.

  A fifth defect belongs to the harness rather than to the box, and it is the third of its kind this branch found: **three of the eight checks could not fail on a box that had been used before.** `drive-write` gated on a fixed probe file nothing removes, with `smbclient`'s exit status printed and discarded; `drive-ingested` grepped a container log that outlives a restart for that same fixed name; and `box-on-mesh` gated on a headscale registration the lab keeps between runs. All three are fixed after the run they qualify — the probe is now a new file with new contents every run and is removed from the drive afterwards, `drive-write` gates on `smbclient`'s status and on the `NT_STATUS` line it prints, and the two new predicates are extracted from the script and driven against fixtures by `deploy/coordinator/tests/test_lab.py`, the way `CITED_CMD` and `ROUTINE_LINE_RE` already were. The third was found by sweeping the other rows for that same shape, and it is why run 3's honest count is five of eight: `box-on-mesh` now gates on the node being `online` rather than merely listed. None of this has run end to end: the fixed harness produces run 4, which will be the first table in which every row is its own measurement.

  So P2's promise — a member at home, behind a NAT that forwards no UDP, writing to a department drive and getting a cited answer out of it — is proven, and so is the routine on the end of it. Details in `.superpowers/sdd/2026-09-09-nufi-box-p2/task-9-report.md`, `task-10-report.md` and `task-9c-report.md`.
- Not done in P2, and deferred deliberately: the field test on a real VPS with a public DNS name and a Let's Encrypt certificate. The coordinator has only ever run against Caddy's internal CA in the Docker lab. That is **P3 Task 1**.

### P3 · A department for a week · Oct 16–29

Goal: one real internal department uses the box for its actual work for five working days.

- **Task 1 — the coordinator in the field.** Stand one up on the VPS asked for in P0, with a public DNS name and a Let's Encrypt certificate, and re-run the day-at-home acceptance against it from a real laptop on a real hotspot. Everything below it is proven in a Docker lab and nothing else. Runbook: `deploy/coordinator/README.md`.
- **Two fixes that belong in `apps/nufi-agent`, not in the box.** P2 pushed both into the Studio image and neither can be closed from `deploy/box`:
  - **Members signing in over SSO see zero routines.** Proven live: the supported path (`/enter/studio`) makes even the box admin a JIT non-superuser Studio account that lists 0 flows, while the superuser holds all four — `create_flow` hard-codes the owner and the shared folder has `user_id=NULL`. Cheapest fix: seed the flows in `_initialize_jit_user_defaults` the way variables already are. Until it lands, the department routines are an admin-only feature.
  - **Nothing can cap a routine's generation from the flow.** The Studio Ollama component exposes no `num_predict` and its `Timeout` input is a dead knob (langchain-ollama 0.3.10's `ChatOllama` has no such field, so pydantic drops it), so a generation that does not emit a stop token runs until something unloads the model, and outlives the client that started it — watched live at 39,000 tokens in one run and past 40,000 in another, with llama.cpp shifting context to keep going. `weekly` itself did return in 7 s on the third run, so this is a hazard rather than a certainty. The 40,000-token runaway was an agent question, which the gateway's 600 s `request_timeout` would have cut; the routines bypass the gateway, which is why they are the case with no backstop. Two lines in `apps/nufi-agent`, plus run cancellation.
- Scheduler (G); backup (P); the remaining recipes that do not need email.
- Run the Legal, HR, General Affairs and Strategy weeks with real documents; write each up with its evidence, the way the eight existing scenario posts are written.
- Acceptance: five days without an engineer touching the box; every problem in an issue; the department's own verdict recorded.

### P4 · Sellable · Oct 30 → Nov

- `nufi-box` complete (N); updater (O); the hardware list booted and timed on the two SKUs (Q); remote-support switch; the customer guide in `apps/docs` written from a level-1 install performed by a developer outside the team, with the clock running.
- First external pilot, on a PC we install at our desk (level 3). This lines up with the appliance roadmap's v1.0 in December.
- Later, only if customers bring their own hardware in numbers: the USB image and browser wizard (level 2).

## 5. What changes where (all in this repo)

- `deploy/box/`: `docker-compose.yml` (box tier), `docker-compose.standard.yml`, `docker-compose.full.yml`, `.env.example`, `install-box.sh`, `nufi-box` (the day-two command), `bundle/` (what the offline bundle contains).
- `deploy/coordinator/`: headscale + Caddy compose for `mesh.nufi.me`, and its runbook.
- `deploy/platform/adapters/`: the three MeshBox adapters stay as they are, for the day the appliance portal wants to sit in front; `nufi-ingest/` and `nufi-cron/` join them.
- `apps/admin-panel`: Network page, Drives page, remote-support switch, update status. No wizard; the installer's four questions are the first run.
- `apps/chat`: team ↔ drive mapping for RAG scope; nothing else.
- `.github/workflows/box-release.yml`: images and the signed bundle, on `nufi-box-v*`.
- `apps/docs/content/docs/deployment/box/`: hardware list, install in 15 minutes, join a laptop, drives, updates, backup, support, troubleshooting. Written from a timed install by a developer outside the team, and kept to what that person actually needed.
- `deploy/platform/scenarios/`: `--box` acceptance run; the recipe flows; the department weeks below as runnable steps.

## 6. Department scenarios: a week with a PC, a drive, chat and an agent

Each uses all three tools the request names, says what the admin sees, and marks the phase at which every step works. The Q&A checks already in `departments.json` are the regression test under each story.

### Legal · contracts and renewals

*People:* a team lead and two staff. *Drive:* `\\nufi\legal` with `contracts/`, `templates/`, `nda-drafts/`.

| Day | What they do | Tool | From |
|---|---|---|---|
| Mon | Copy the year's 40 supplier contracts into `contracts/`. Each becomes knowledge within a minute; nobody uploads anything twice. | drive → ingest | P1 |
| Mon | "Which contracts auto-renew in the next 90 days, and what is the notice period for each?" The answer lists the contracts with the clause quoted and the file named. | chat + RAG | P1 |
| Tue | "Draft an NDA for a Vietnamese subcontractor from our template, mutual, three years, Korean law." From `templates/nda-ko.docx`; saved to `nda-drafts/`. | chat | P1 |
| Wed | Routine **Risky-clause review** on a new contract picked from the drive: unlimited liability, unilateral termination, foreign governing law, with page references. | agent + input | P2 |
| Fri | Routine **Renewal tracker**, weekly: writes `renewals-this-quarter.md` to the drive. | agent + schedule | P3 |
| any | "What did Finance pay this supplier?" is outside Legal's documents and is refused, not invented. | RAG refuse check | P1 |

*Admin sees:* who asked what, which files each answer cited, that nothing left the box.

### HR · policies, hiring and onboarding

*Drive:* `\\nufi\hr` with `policies/`, `applicants/<role>/`, `onboarding/`. `applicants` is readable by HR only and its knowledge never appears in another department's answers.

| Day | What they do | Tool | From |
|---|---|---|---|
| Mon | A new hire asks the helpdesk bot "how many days of annual leave in year one, and do unused days carry over?" Cited from `policies/leave.pdf`. | chat + RAG | P1 |
| Tue | Twelve résumés land in `applicants/backend/`. Routine **Applicant summary**: one table, one row per résumé; identifiers masked before the hiring manager sees it. | agent + PII masking (full tier) | P2 / P3 |
| Wed | "Draft an offer letter for the second candidate, senior level, Seoul, start November 1." From `onboarding/offer-template.docx`. | chat | P1 |
| Thu | "What is the probation period for contractors?" The policy covers employees only; the box says so. | RAG refuse check | P1 |
| Fri | Routine **Onboarding checklist**, triggered by a new file in `onboarding/new/`. | agent + event | P3 |

### General Affairs · facilities, notices, vendors

*Drive:* `\\nufi\ga` with `leases/`, `manuals/`, `notices/`, `vendors/`.

| Day | What they do | Tool | From |
|---|---|---|---|
| Mon | "When does the 4F lease end and what is the renewal notice deadline?" Cited from `leases/4f.pdf`. | chat + RAG | P1 |
| Tue | Draft the Chuseok closure notice in Korean, then English and Vietnamese for the Hanoi team; save all three to `notices/`. | chat | P1 |
| Wed | "Which vendor services the air conditioning and what is the maintenance interval?" From `vendors/` and `manuals/`. | chat + RAG | P1 |
| Thu | Routine **Renewal tracker** over `leases/` and `vendors/`: every end date in the next 120 days. | agent + schedule | P3 |
| Fri | A question about the parking policy has no document; the box says so. GA adds the PDF; the same question now answers. | ingest loop | P1 |

### Corporate Strategy · research, meetings, reports

*Drive:* `\\nufi\strategy` with `research/`, `meetings/`, `reports/`.

| Day | What they do | Tool | From |
|---|---|---|---|
| Mon | Drop six market reports into `research/`. "Summarise what these say about NPU adoption in Korean enterprises in 2026, with sources." Each claim cites a file and page. | chat + RAG | P1 |
| Tue | Paste the transcript of Monday's leadership meeting. Routine **Meeting summary and actions**: decisions, owners, deadlines; saved to `meetings/2026-09-15.md`. | agent + input | P2 |
| Wed | "Compare our pricing assumptions in `reports/q3-plan.pdf` with the market rates in the research." The box quotes both sides; the reader judges. Retrieval grounds finding, not reasoning, and the evidence file says so. | chat + RAG | P1 |
| Thu | Routine **Weekly report draft**, Thursday 17:00: assembles the week's `meetings/` and new `research/` into a draft in the department's tone. | agent + schedule | P3 |
| Fri | Web search is off; a question about yesterday's news is answered with "no document covers this". Search is a gateway option that leaves the air gap and is switched on knowingly. | boundary | P1 |

Finance, Sales, Support and Engineering keep their existing Q&A evidence and get their week after these four have run for real.

## 7. The product introduction, claim by claim

`marketing/NuFi_Team_Product_Intro_EN.html` against what runs. ✅ true on the box tier at P1 · ⚠️ true with a condition the page should state · ❌ not built.

| Claim | Verdict | Note |
|---|---|---|
| Fully air-gapped | ⚠️ | True with `ollama` or `remote`. Updates and the mesh coordinator are outbound-only and carry no documents; say "air-gapped by default, updates opt-in". |
| $0 monthly fees | ✅ | For the customer. Dudaji pays for the coordinator and update host. |
| Remote access without a static IP | ⚠️ | Through our coordinator; field test after P2. |
| Korean-NPU compatible | ⚠️ | RNGD experience is real; the stack has no tested RNGD profile yet. "Option" is the honest word already used. |
| 99.08% Korean PII recall | ⚠️ | Full tier only. |
| No IT approval needed | ✅ | Power and LAN, outbound only. Except: a company laptop locked by IT cannot install the client. |
| 01 Drive · 02 RAG Q&A · 03 Semantic search · 04 Chat · 06 Drafts · 15 Shared inference · 16 Access & audit | ✅ | Box tier after P1 / P2. |
| 05 Bulk document processing | ⚠️ | A Studio flow over a drive folder at P3; say "via routines". |
| 07 Meeting support "recording → summary" | ⚠️ | From a transcript at P2. No recording or transcription on the box. |
| 08 Quick data analysis (CSV) | ❌ | The app's code execution is a hosted API. Remove or mark "roadmap". |
| 09 PII masking | ⚠️ | Full tier. |
| 10 Scheduled routines · 11 Event-triggered | ❌ → P3 | |
| 12 Web search via gateway | ⚠️ | Leaves the air gap; already worded as optional. |
| 13 Email integration "included" | ❌ | **Nothing reads or sends mail.** Change to "planned" now. |
| 14 ERP / groupware via skills | ⚠️ | Studio speaks MCP; "standard connectors for major ERPs" do not exist. |
| Recipes: doc Q&A ✅ · helpdesk ✅ · meeting summary ⚠️ P2 · weekly report ⚠️ P3 · PII masking ⚠️ full · morning inbox ❌ | | Inbox depends on 13. |
| "Small team 5–15 concurrent users" | ⚠️ | The GPU SKU. A PC without a GPU serves 2–3. |
| "Power → LAN → Go" | ⚠️ | True for the pre-installed PC (level 3). Customer-prepared hardware is "Ubuntu → one command → Go" and needs a basic developer for an hour. |
| Setup times (20–40 min) | ⚠️ | Measure in P3 and P4 with a non-engineer and print real numbers. |

## 8. Hardware, honestly

"Good enough hardware" has to mean a short list we have booted our image on, not a minimum spec a customer interprets.

| SKU | Hardware | Tier | Serves | Users |
|---|---|---|---|---|
| Demo Mac | Apple Silicon, 24 GB (7B) or 48 GB (14B), Ollama on Metal | box | fast enough to film; the drive is macOS File Sharing; not sold | 2–5 |
| Dogfood PC | any x86 PC or wiped laptop, 16–32 GB RAM, no GPU | box | chat, drive, RAG on 7B Q4 at CPU speed; slow on camera | 2–3 |
| Team | small-form-factor desktop, 64 GB RAM, one 24 GB NVIDIA GPU, 1 TB NVMe | box or standard | 7B–14B at interactive speed; Studio routines; the brochure's "small team" | 5–15 |
| Secure | Team + 32 GB RAM | full | + Korean PII detection, injection scan, monitoring | 5–15 |
| NPU | RNGD server | any | The Korean-NPU option; needs its own tested profile before sale | per deal |

Minimum the installer enforces: x86-64, 32 GB RAM, 500 GB free, wired Ethernet. Below that it stops and says which line failed. Two exact models for Team and Secure are chosen in P4 after we have booted them.

## 9. Risks

- **The board is personally building the mesh module.** Shipping our own from nufi-app must be said out loud in P0 and left to the board to decide, not discovered in a demo.
- **The VPS is the long pole for P2**, whichever repo the mesh lives in.
- **Korean quality and speed of a 7B model.** Drift to Chinese is fixed by pinning temperature and seed; CPU speed is not fixable. Film on the Team SKU.
- **Hardware sprawl.** Every extra GPU generation or Wi-Fi chip is a support case. Two recommended SKUs, and the installer warns outside them.
- **Locked corporate laptops.** The client needs admin rights on Windows. Document it, and sell the pre-installed PC with the customer's IT in the room.
- **Scope creep from the 17 use cases.** The milestone is four departments and six recipes. Email, CSV analysis and ERP connectors are after P4.
