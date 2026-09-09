# NuFi box

A NuFi box is the NuFi app, its gateway, retrieval, and NUFI Studio, running
on one machine on your LAN. This guide is written for a basic developer or IT
person installing it, with this file open next to a terminal.

## 1. What you get

One install gives you four products, all reachable in a browser, all behind
the same login:

| Product | URL | What it is for |
|---|---|---|
| Chat | `https://<box>:3080` | The NuFi app: chat, agents, file search |
| NuFi Console | `https://<box>:3001` | Identity and single sign-on between the other three |
| NuFi Admin Panel | `https://<box>:3002` | User and model administration |
| Studio | `https://<box>:7860` | NUFI Studio, reached from Chat via Account → Agents → NUFI Studio |

`<box>` is the box name you choose at install, followed by `.local`
(default `nufi.local`).

Each department gets a folder on disk. A file dropped into that folder
becomes that department's knowledge within a minute — see
[Departments and drives](#5-departments-and-drives). There is one admin
login, created during install, that works across all four products.

## 2. Requirements per OS

| OS | What the installer needs already there | What it installs for you |
|---|---|---|
| Ubuntu 24.04 | `curl`, `openssl` | Docker Engine, the NVIDIA container toolkit if a GPU is present |
| macOS | Homebrew | OrbStack (or Docker Desktop) and Ollama, both via `brew` |
| Windows 10/11 | WSL2 with an Ubuntu distro; run the script **inside** that Ubuntu shell | same as the Ubuntu row, from inside WSL2 |

Running the script directly on Windows (not inside WSL2 Ubuntu) fails with
`unsupported OS`.

Hardware: 32 GB RAM, 500 GB free disk, wired Ethernet. A GPU is not required
but is strongly recommended — a 7B model on CPU only is slow enough to
notice in a demo.

On macOS, give Docker Desktop (or OrbStack) at least 12 GB of memory:
Settings → Resources → Memory. The installer warns if the Docker VM has less
than 11 GB. The box itself uses about 3 GB once it is running; the 12 GB
minimum leaves headroom for a second app on the same VM.

## 3. Install

From a checkout of this repo:

```bash
cd deploy/box
./install-box.sh --yes
```

Drop `--yes` to be prompted instead of taking every default. (The hosted
one-liner `curl -fsSL https://get.nufi.me/box | bash` is planned but not live
yet — install from a checkout for now.)

The installer asks four questions:

| Question | Default | What it decides |
|---|---|---|
| Box name | `nufi` | The LAN hostname (`<name>.local`) and a TLS certificate name |
| Admin email | `admin@<name>.local` | The one login you use across all four products |
| Departments | `legal,hr,ga,strategy` | One drive folder, one team, one agent created per name |
| Inference profile | `ollama` (macOS) or `ollama-docker` (Linux) | Where the chat model runs — see [Inference profiles](#6-inference-profiles) |

Choosing an inference profile asks one or two follow-up questions (the model
name, and for `remote`/`cloud` a base URL and API key).

The installer then writes `.env`, starts the stack, pulls the model, creates
the admin login, and prints a banner:

```
  NuFi box "nufi" is up.

  Chat:        https://nufi.local:3080     (also https://<box-ip>:3080)
  Agents:      https://nufi.local:3001/choose
  Console:     https://nufi.local:3001
  Admin panel: https://nufi.local:3002
  Certificate: http://nufi.local/   ← laptops trust it once

  Admin login: admin@nufi.local / <generated password>
  Drives:      <data dir>/drives/<department>  → become that department's knowledge

  Day two:     nufi-box status | logs | drive add <name> | ca-cert | doctor
```

That banner is the whole result: four URLs, one login, and where the drive
folders live. On a machine that already has the images and models local,
install takes about **75 seconds**. On a first install that has to download
everything, budget about 15 minutes on an office network — most of that time
is the download, not the install itself.

On a blank Ubuntu 24.04 (4 vCPU, 8 GB) — no Docker, no checkout, nothing
mounted — the whole install was measured end to end, with the NuFi images on a
LAN registry and everything else off the internet: **25 min 40 s from the
first command to the banner**, one department, the `ollama-docker` profile.
Docker Engine is installed, the box re-runs itself inside the new `docker`
group, and the first image starts coming down inside the first **two
minutes**; nearly all of the rest is download. A LAN mirror does not make that
much shorter — the NuFi images come off it in a couple of minutes, while the
third-party ones (Studio, ollama, the RAG API) still come from Docker Hub and
ghcr.io at whatever the office network gives you.

Budget **about 30 GB of free disk**. At the banner that VM had 29 GB of its
38 GB root filesystem in use — 25 GB of images, 2 GB of volumes, the rest
Ubuntu itself — and that is with a *single* department; the default four
share the same images but add their own drives and collections. Memory
settled at 5.7 GB of 8 GB while the box was answering, with no swap: 8 GB
runs a one-department box on CPU with nothing to spare.

`deploy/box/tests/vm/` holds that run as a recipe (`run-ubuntu-install.sh`,
`lima-ubuntu.yaml`): it installs onto a blank machine, prints the wall time,
and fails if the banner never appears. `verify-ubuntu-box.sh` next to it does
the other half from the Mac — `/health` over TLS, a document dropped in a
drive reaching the agent, and that agent answering with a citation.

Re-running `./install-box.sh` is safe: it keeps `.env` and every answer you
already gave, and only asks again for anything you did not set.

Once the banner prints, open the Chat URL in a browser, trust the
certificate if the browser warns about it (next section), log in with the
admin login, and send a message.

### Boxes without GitHub access

Every NuFi image (`nufichat`, the admin panel, console, litellm, ingest,
studio) normally comes from `ghcr.io/dudaji-vn`. A customer box, or any
machine that cannot `docker login ghcr.io`, cannot pull those. Instead, run
a small registry on a machine that already has the images — a Mac that
built them — and point the box at it.

Such a box usually has no checkout either. Make one from a machine that has
the repo and carry it over (scp, a USB stick — no GitHub involved):

```bash
git archive -o box.tar HEAD \
  deploy/box deploy/platform/scenarios deploy/platform/adapters/nufi-ingest docs
```

and on the box, `tar xf box.tar && cd deploy/box`.

On the Mac with the images:

```bash
make -C deploy/box registry-up   REGISTRY=<mac-ip>:5001
make -C deploy/box registry-push REGISTRY=<mac-ip>:5001
```

Port 5001, not 5000: macOS runs AirPlay Receiver on 5000 (System Settings →
General → AirDrop & Handoff), and the registry would silently lose the port.
`REGISTRY` is the address the *box* will use; the push itself goes over
`localhost`, the one address Docker trusts without an insecure-registries
entry, so Docker Desktop needs no change and no restart. The push also
renames the images to the tags a default install asks for (`main`, and
`box-main` for studio), whatever they are tagged locally, and it mirrors the
two third-party images that live on ghcr.io as well (the RAG API and Samba) —
without those a box that cannot reach GitHub gets most of the way through an
install and then stops.

On the box:

```bash
./install-box.sh --yes --registry <mac-ip>:5001
```

`<mac-ip>:5001` has no certificate, so Docker refuses to pull from it until
it is marked insecure. On Linux the installer does this for you: it writes
(or merges into) `/etc/docker/daemon.json` —
`{"insecure-registries": ["<mac-ip>:5001"]}` — and restarts Docker;
`--dry-run` prints the plan instead of touching the machine. On macOS
(Docker Desktop), the installer only prints the step — add the registry
yourself under Settings → Docker Engine → `insecure-registries`, then
Apply & Restart.

## 4. Trust the certificate

The box signs its own certificate — nothing calls out to a public
certificate authority — so a browser sees it as untrusted until it trusts
the box's own CA. This is not optional: both Chat and NuFi Console set
`Secure` session cookies, and Studio needs `https` to reach Console's JWKS
endpoint for single sign-on, so plain HTTP does not work for logging in.

The install script trusts the CA in your own login keychain automatically
on macOS. On any other machine — the box itself on Linux, or a colleague's
laptop on the same LAN — do it by hand:

1. Open `http://<box>/` in a browser (plain HTTP, no port). It is a landing
   page with a certificate download link.
2. Download `nufi-box-ca.crt` and trust it as a certificate authority in
   your OS or browser's certificate store.
3. Reload the Chat URL. The warning is gone.

On macOS you can also trust it from a terminal:

```bash
security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db \
  deploy/box/data/nufi-box-ca.crt
```

`nufi-box ca-cert` prints the exact path to the certificate file on this
box, and the URL to give a colleague.

If `nufi.local` does not resolve on a machine (some networks block
`.local` / mDNS), use `https://<box-ip>:3080` instead — the certificate
covers the box's IP address as well as its hostname, so this is not a
downgrade, just a different name for the same certificate.

## 5. Departments and drives

Every name you gave at the "Departments" question becomes a folder:

```
<data dir>/drives/<department>/
```

Drop a file into that folder and it becomes searchable knowledge for that
department's agent. Supported types are PDF, DOCX, PPTX, XLSX, plain text
(`.txt`), Markdown, CSV, JSON and HTML. Anything else in the folder is
ignored, as are lock and metadata files (`~$…`, `.DS_Store`).
Expect **32–97 seconds** from dropping a file into a department used for the
first time to it being searchable (the daemon has to create the team and
agent as well as embed the file); a file dropped into a department that is
already active embeds in well under a minute. Once embedded, asking about it
is instant — no re-embedding on every question.

Add another department later without reinstalling:

```bash
./nufi-box drive add finance
```

This creates the folder and share; the watcher creates the team and agent
on its next scan, about 20 seconds later.

By default the daemon that watches the drives runs **as the admin**, so the
admin who installed the box already owns every department's team and agent
and sees them immediately after logging in. Nobody else does. To let a
colleague use a department's agent, log in as the admin, open **Teams** in
the app, and invite them to that department's team — installing the box
does not add anyone else automatically.

## 6. Inference profiles

| Profile | Where the model runs | Trade-off |
|---|---|---|
| `ollama` | Ollama on the host machine (macOS default; Linux default too, but only when Ollama is already installed on the host) | Fastest to set up on a Mac — no extra container, uses Metal — but ties the model to this one host |
| `ollama-docker` | An Ollama container started by the box compose (Linux default otherwise) | Self-contained inside the box's own stack, but adds a container and its own model pulls |
| `remote` | Any OpenAI-compatible server on the LAN (vLLM, RNGD, TGI) | Offloads inference to real hardware elsewhere; the box stays light, but now depends on that server already running |
| `cloud` | An external API provider | Needs no local model at all, but prompts leave this machine — the box is no longer air-gapped |

A GPU on a Linux box only changes which compose layer is applied
(`docker-compose.gpu.yml`, for the NVIDIA container toolkit) — it does not
change which of `ollama` or `ollama-docker` gets picked.

### What to expect from a 7B model

The default profile ships with `qwen2.5:7b`. In a live acceptance run across
32 questions over eight departments, at temperature 0 with a fixed seed, it
answered **10 of 32** correctly — identical across two back-to-back runs
(0/32 answers differed). The plumbing was not the problem: every department
ingested, retrieval found the right passage, and the citation was correct
whenever one appeared. What failed was the model itself — stating a number
the retrieved passage did not contain, occasionally answering in Chinese
mid-sentence for a Korean question, or not calling file search at all. If
accuracy matters more than running fully on CPU, use a larger
`INFERENCE_MODEL` on a box with a GPU; that is the lever that moves this
score, not more prompt tuning.

## 7. Day two

`nufi-box` is the one command for running the box day to day. It lives next
to `install-box.sh` and is also symlinked onto your `PATH`.

| Verb | Does |
|---|---|
| `status` | Every service's health, the model in use, disk space, drive path |
| `logs [service]` | Follow logs for everything, or just one service |
| `drive add <name>` | Create a new department: folder, share, team and agent |
| `ca-cert` | Print the path to the box's certificate and where to fetch it |
| `doctor` | Check the things that usually break, in plain words |
| `up` / `down` / `restart` | Start, stop, or restart the whole box |
| `invite <name> [--os win\|mac\|linux] [--drives a,b]` | Write a one-file join for a new laptop — see [From home](#8-from-home) |
| `members` | List the laptops currently joined to the mesh |
| `revoke <name>` | Remove a laptop's access to the mesh |
| `update` / `backup` / `support` | Not built yet — see [What is not in P1](#10-what-is-not-in-p1) |

## 8. From home

A laptop on an LTE hotspot, at a hotel, or anywhere off the office LAN can
still reach the box — once it has joined the mesh coordinator (`nufi-box
mesh up` gives the box a stable mesh address and sets `BOX_MESH_HOST` in
`.env`; `invite` refuses with a clear message if that has not happened
yet).

### For the admin: inviting a laptop

```bash
./nufi-box invite alice --os macos --drives legal,hr
```

- `NAME` is anything short and legible — it becomes the join file's name and
  the row you will see in `nufi-box members`.
- `--os windows|macos|linux` picks the join file's format (default `macos`).
- `--drives a,b` picks which department drives the file maps (default:
  every department in `DEPARTMENTS`).

This mints a single-use, one-hour pre-auth key from the mesh coordinator and
writes `data/invites/nufi-join-alice.<ext>` (mode `0600` — readable only by
whoever runs the box). The command prints the path and a sentence to send:

> Send it to alice (email or chat — not a public link): "Run this file, then
> open https://nufi.\<mesh\>:3080 — the key inside works once."

`nufi-box members` lists everyone currently joined — name, mesh IP, online,
last seen, and the headscale user. `nufi-box revoke alice` removes her
node; her laptop can no longer reach the box until invited again.

### For the member: joining from a laptop

1. Install the official Tailscale app first — the join file checks for it
   and prints the download link (`https://tailscale.com/download`) if it is
   missing.
2. Run the file the admin sent you: double-click the `.command` file on a
   Mac, the `.sh` file on Linux, or the `.cmd` file on Windows. It trusts
   the box's certificate, connects to the mesh, maps the drives you were
   given, and opens chat.
3. The key inside the file is single-use — if it does not work, ask the
   admin to run `nufi-box invite` again for you.

**If your laptop is already enrolled in a corporate Tailscale tailnet**, the
join file will not work: Tailscale logs into one control server at a time,
and a corporate MDM profile usually locks that choice. Ask your IT team, or
join from a personal device instead.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| Install fails with "port is already allocated" for 3080, 3001, or 4000 | Something else on this machine already uses that port. Either stop it, or install the box on remapped ports with `NUFI_BOX_COMPOSE_EXTRA` — see below. |
| `https://nufi.local:3080` does not load; the browser cannot find the host | `.local` (mDNS) does not resolve on this network. Use `https://<box-ip>:3080` instead — the certificate covers the IP too. |
| The browser warns the certificate is not trusted | You have not trusted the box's CA on this machine yet. Open `http://<box>/` and follow [Trust the certificate](#4-trust-the-certificate). |
| A department's agent is not in the app | You are not the admin and were not invited to that department's team. Ask the admin to invite you from Teams in the app — see [Departments and drives](#5-departments-and-drives). |
| A file with a Korean name shows garbled ("mojibake") characters in citations | Fixed in the shipped `nufi-ingest` image (the filename is now percent-encoded on upload, matching what the app's own web client sends). If you still see it, you are running an older image — pull the latest one. |
| A Studio flow fails with `SSRF Protection: Hostname … resolves to blocked IP address(es)` | Studio's model node reaches the model through `host.docker.internal` (macOS) or `ollama` (Linux) — both private addresses, which Langflow blocks by default. The box's shipped compose file already allow-lists exactly those two hostnames (`LANGFLOW_SSRF_ALLOWED_HOSTS`). If you see this, you are running a compose override that dropped that setting — go back to the shipped `docker-compose.yml`. |
| The installer warned the Docker VM is too small, or the box is slow and `nufi-box doctor` shows failing health checks | `doctor` has no memory probe of its own — the installer's prerequisite check is what reports the Docker VM's size, at install time. A box that is swapping heavily shows up indirectly instead: answers get slow, and `doctor`'s `curl` health checks start failing. Give Docker Desktop / OrbStack more memory: Settings → Resources → Memory, at least 12 GB on macOS. Studio alone is more than a third of the box's own footprint; running something else heavy on the same VM is the usual cause. |
| After a reboot, `nufi.local` stops resolving | The installer announces the name on the LAN with a background `dns-sd` (macOS) or `avahi-publish` (Linux) process, and neither is installed as a service, so a reboot ends it. Re-run `./install-box.sh --yes` to announce it again — it keeps every answer and secret — or use `https://<box-ip>:3080`, which the certificate covers too. |
| The box's IP changed and the browser now says the certificate does not cover this address | The certificate's IP entry is fixed at install time from the address the box had then, so a new DHCP lease invalidates it. Re-run `./install-box.sh --yes`: it re-reads the current address and re-issues the certificate, keeping every answer and secret. A DHCP reservation for the box stops it happening again. |
| Right after the first install on Linux, `nufi-box` (or any `docker` command) says `permission denied while trying to connect to the docker API` | The installer put you in the `docker` group, but a group only reaches a shell at login. The install itself is fine — it re-ran inside the new group to finish — and your own shell catches up when you log out and back in, or immediately with `newgrp docker`. |
| The banner's `https://<box-ip>:3080` is not the address other people on the LAN use | The certificate's IP is the first address `hostname -I` prints, which on a machine with two networks (two NICs, a VPN, a VM) need not be the one colleagues reach. Use `https://<box>.local:3080` — the same certificate covers the name — or give the box a single LAN address and re-run the installer. |
| The install stops with `could not pull the images after 3 attempts` | Every image comes over the network, and the installer already retried the whole pull three times. Check the machine still has a route out (and, on a `--registry` box, that the registry machine is awake), then re-run `./install-box.sh --yes` — it keeps every answer and picks up where the download left off. |
| You changed the admin password and wonder whether the drives will still ingest | They will. The ingest daemon learns the account's id at its first login and keeps it in its own state volume, so it never presents the password again — a password change is invisible to it. The password is read again only if that state volume is reset (`docker volume rm nufi-box_ingest-state`), so if you change it, change `ADMIN_PASSWORD` / `INGEST_PASSWORD` in `.env` too. |
| `nufi-box logs nufi-ingest` is full of `scan failed: POST /api/auth/login -> 404: Email does not exist` | Normal during an install, and only during one. The ingest daemon starts with the rest of the stack, several minutes before the installer creates the account it logs in with, so every scan until then fails and says so. It backs off while it waits and starts ingesting on its own once the account exists — the last line will be `logged in as …`. If those errors are still arriving well after the banner, the password in `.env` and the account no longer match: see the row about changing the admin password. |
| `nufi-box doctor` shows `!!` on `jwks.json` | The console's OIDC signing key is malformed. Re-run the installer (`./install-box.sh --yes`) — it regenerates the key and keeps every other answer and secret. |

### Installing next to something else that already holds 3080 / 3001 / 4000

Rather than stop the other service, layer a small compose file that remaps
only Caddy's host-side ports. It is not part of this repo — keep it
somewhere local to this machine, for example:

```yaml
# local-ports.yml
services:
  caddy:
    ports:
      - "13080:3080"
      - "13001:3001"
      - "13002:3002"
      - "17860:7860"
      - "14000:4000"
      - "10080:80"
```

Then point every box command at it:

```bash
NUFI_BOX_COMPOSE_EXTRA=/path/to/local-ports.yml ./install-box.sh --yes
NUFI_BOX_COMPOSE_EXTRA=/path/to/local-ports.yml ./nufi-box status
```

Nothing inside the box changes — the app still talks to itself on
3080/3001/3002/7860/4000 as usual. Only the ports this host exposes move.
Drop `NUFI_BOX_COMPOSE_EXTRA` and run `nufi-box up` again once the other
service is stopped, to get back onto the real ports.

## 10. What is not in P1

This install gives you a box on your own LAN. The following are not built
yet:

- **Remote access.** `nufi-box invite`/`members`/`revoke` (see
  [From home](#8-from-home)) are the admin side of joining a laptop to the
  box's mesh; bringing the box itself onto a mesh coordinator (`nufi-box
  mesh up`) is a separate piece landing alongside this one.
- **`nufi-box update`.** There is no signed update bundle or rollback yet;
  upgrading means pulling new images and running the installer again.
- **`nufi-box backup`.** There is no scheduled backup yet.
- **NUFI Works.** Only NUFI Studio runs on the box; Works stays in the
  cloud — it needs infrastructure a box cannot provide.
- **Scheduled routines and routine input.** A Studio flow runs as built; it
  does not yet take a per-run input from the app, and nothing runs it on a
  schedule.
- **The acceptance score is a measurement of the model, not the box.** The
  10/32 figure above says how good `qwen2.5:7b` is at these questions. It
  does not say whether ingestion, retrieval, or citation work — those
  passed in full.
