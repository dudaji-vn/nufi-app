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
| Box name | `nufi` | Yours to choose: the LAN hostname (`<name>.local`), the mesh hostname (`<name>.<base domain>`) and the certificate name. Lowercase letters, digits, hyphens. The installer refuses a name another machine on the network already answers to; `mesh up` and `invite` refuse a name the coordinator already lists — two boxes, or two laptops, cannot share one |
| Admin email | `admin@<name>.local` | The one login you use across all four products |
| Departments | `legal,hr,ga,strategy` | One drive folder, one team, one agent created per name |
| Inference profile | `ollama` (macOS) or `ollama-docker` (Linux) | Where the chat model runs — see [Inference profiles](#6-inference-profiles) |

Choosing an inference profile asks one or two follow-up questions (the model
name, and for `remote`/`cloud` a base URL and API key).

The installer then writes `.env`, starts the stack, pulls the model, creates
the admin login, and prints a banner. `.env` is created mode **0600** before a
byte of it exists and is kept there by every later write: it holds the admin
password, the database passwords, the JWT secrets, the console's signing key,
the Samba password, the box's Studio key, and — on a mesh box — the
coordinator API key, which is a credential for every box on that coordinator.

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
the repo and carry it over (scp, a USB stick — no GitHub involved). The same
three directories `update` fetches: `deploy/box` plus the two it depends on —
`nufi-box flows install` needs the builder in `deploy/platform/scenarios`
(the whole directory: `build_flows.py` imports `run_box` and `run`, both
siblings of `studio/` at its root, not inside it), `nufi-box schedule list`
needs the adapter in `deploy/platform/adapters/nufi-cron` — or the install
finishes with "the routines are not in Studio yet":

```bash
git archive -o box.tar HEAD \
  deploy/box deploy/platform/scenarios deploy/platform/adapters/nufi-cron
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

**Who owns the files.** On Linux the drives are shared by a Samba container,
and it writes as the same uid that installed the box (`NUFI_SMB_UID` in
`.env`, taken from `id -u`; a root install uses 1000 instead). So a file a
member drops in from a laptop is owned by the box's admin, exactly like one
the admin copies in by hand. If a member gets `NT_STATUS_ACCESS_DENIED`
writing to a share — a box whose drives were created by a different user than
the one running the installer — re-run `./install-box.sh`, which puts the
drives back in step, or give them to that uid by hand:

```bash
sudo chown -R "$NUFI_SMB_UID:$NUFI_SMB_GID" <data dir>/drives/<department>
```

Re-running the installer keeps that answer rather than taking the drives for
whoever ran it, so a colleague repairing the box does not lock the admin out.
Handing the box to a new owner is a thing you say out loud:

```bash
NUFI_SMB_UID=$(id -u) NUFI_SMB_GID=$(id -g) ./install-box.sh --yes
```

By default the daemon that watches the drives runs **as the admin**, so the
admin who installed the box already owns every department's team and agent
and sees them immediately after logging in. Nobody else does. To let a
colleague use a department's agent, log in as the admin, open **Teams** in
the app, and invite them to that department's team — installing the box
does not add anyone else automatically.

### The four routines that read them

The installer also puts four **routines** into NUFI Studio — flows a person
can open, run and edit, that read the same drive folders:

| Routine | What it does |
|---|---|
| `Routine · ask the department drive` | Answers a question from that department's documents and names the file it answered from |
| `Routine · meeting transcript to decisions` | Paste a transcript, get the decisions with an owner and a deadline against each one |
| `Routine · HR helpdesk from the policy` | Answers strictly from the HR drive, cites the policy file, refuses when the policy is silent |
| `Routine · weekly report from the drive` | Drafts the department's weekly report from what is on its drive, citing each file — see the caveat below |

**What `weekly` does not do.** It reads the **whole** department drive, not
just this week's files. The period you ask for ("9월 첫째 주") is a line in the
prompt, so it is the model that decides which of the drive's documents belong
to that week — the flow does not filter by a file's modification date, and no
component in this Studio build exposes one (the Directory node hands on a
file's path and its text, nothing more). Read the dates in the draft before
sending it, and keep a department's drive tidy if the reports matter.

**A routine's length is bounded; an abandoned run is not.** Each of the four
routines carries a ceiling of **2048 tokens** on one generation — far above what
any of them has needed to answer from a department drive, and set on the model
node itself, so it holds however the routine is called. Before that ceiling
existed, `weekly` on `qwen2.5:0.5b` was seen generating past **39,000 tokens**,
long after the caller had given up, holding the model and slowing every other
question on the box.

What is still not bounded is the *client's* side: nothing cancels a run whose
caller has gone, so a routine that is generating keeps going until it reaches
the ceiling. Two things remain true and worth knowing:

* the component's `Timeout` field is **not** a deadline — it is dropped before
  it reaches Ollama, so setting it does nothing;
* chat and the agents are not affected either way: they go through the gateway,
  which has its own 600-second request timeout, and only the routines talk to
  Ollama directly and bypass it.

Practical advice unchanged: run the routines on **`qwen2.5:1.5b` or larger**
(`weekly` answers in about five seconds on 1.5b; 0.5b is the size that rambles),
and if a routine still does not come back, `nufi-box logs ollama` shows whether
the box is generating (`n_gen` climbing with nobody listening); unloading the
model ends it: `docker compose exec ollama ollama stop <model>` on Linux,
`ollama stop <model>` on macOS.

The drive is a field on the flow, not a copy of the flow: the same routine
serves every department. In the canvas, change the **Drive** node's path
(`/drives/legal` → `/drives/finance`, and the index name with it); over the
API, send it as a tweak:

```bash
cd ../platform/scenarios/studio
STUDIO_API_KEY=… python3 run_flows.py --base https://localhost:7860 \
  --cacert ../../../box/data/nufi-box-ca.crt \
  --flows ../../../box/data/studio-flows.json \
  --only docqa --department hr --input "연차휴가는 며칠인가요?"
```

Re-running `nufi-box flows install` is safe: a routine that is already there
by name is kept, edits and all, and only what is missing is created.

**Who can see them.** They are installed into the Studio account of the
superuser the installer created (`ADMIN_EMAIL`, with the Studio password in
`.env` as `STUDIO_SUPERUSER_PASSWORD`) — sign in at `https://<box>:7860`
with those. A member who reaches Studio the usual way, through the app's
Account → Agents → NUFI Studio, arrives as their own Studio account, and
**gets their own copy of every routine** on the way in: Studio scopes flows to
their owner, so each member is seeded rather than shared with. A copy a member
edits is theirs and is never overwritten; one they have not touched follows the
box when a routine is rebuilt.

## Before a demo, or after the box moves network

```sh
nufi-box doctor
```

Ten of its checks go to `localhost`. The eleventh is the one that matters to
everybody else in the room: that `nufi.local` is being announced on the LAN and
points at *this* machine.

The installer publishes that name over mDNS with the address the box had that
day. A new DHCP lease, a different Wi-Fi network, a dock unplugged — and the
name points at a stranger while the box itself is perfectly healthy. `doctor`
used to pass all ten checks in exactly that state, because nothing it asked was
the question a visiting laptop asks.

```
 !!  nufi.local points at 192.168.1.99, this machine is 192.168.1.25 — run: nufi-box announce
```

```sh
nufi-box announce      # re-publish the name at the address the box has now
```

That also writes the new `BOX_IP` into `.env`, so the certificate and the banner
follow the machine.

A laptop joining for the first time still needs the box's certificate once —
`nufi-box ca-cert` prints where it is.

## When something is wrong

```sh
nufi-box doctor              # first — what, in plain words
nufi-box support             # then — package it up to send
```

`doctor` is the first move; it names the thing that's broken. `support` is the
second: it gathers what an engineer actually asks for in the first three
emails of any support thread — the box's version, what's running, `doctor`'s
own output, the last 300 lines of every service's logs, the compose config,
and a few small files (`schedules.ini`, `caddy/mesh.caddy`, a per-department
folder listing, the `data/backup` listing) — into one `.tar.gz` you attach and
send to **support@nufi.me** with whatever you saw.

**What it does not hold.** Nothing in the bundle is a secret. `env-keys.txt`
lists the *names* of every key in `.env` and whether each has a value
(`<set>` / `<empty>`) — never the value, and never a fragment of one: it is
built by reading `.env` as entries, not lines, so a multi-line secret (the
console's signing key is a PEM) is one key here, not one per line of it.
`compose.yml` is `docker compose config` (every `${VAR}` resolved to what a
service actually got) with every value that looks like a secret — a `.env`
key ending in `_KEY`, `_SECRET`, `_PASSWORD`, `PEM`, `TOKEN` or `_IV` —
blanked out wherever it appears, not only under the name that suggested it,
and blanked again by that entry's own name as a second layer. Every other
file in the bundle — every log, `doctor.txt`, `status.txt`, `box.txt` — is
swept for the same secret-looking values before the tar is made, since a
secret does not only ever show up inside `docker compose config`'s own
rendering of it. Drive contents are never read and no document's name ever
leaves the box: the bundle lists each department's folder and how many files
are in it, nothing more.

**What this is not.** `support` packages what the box already knows about
itself into a file *you* send. It does not open a connection from Dudaji into
the box, and nothing on the box listens for one — that remote half does not
exist yet; see [What is not built yet](#10-what-is-not-built-yet).

It works on a box that will not start, one with a failing `doctor`, and one
that has never been backed up — nothing here stops partway because one check
failed; a check that cannot answer says so in the bundle instead
(`(unavailable: …)`) and the rest still gets collected. The one exception is
the sweep itself: it needs `python3`, and if that is missing or broken the
bundle is **not** packed — `support` prints `NOT SWEPT`, leaves the raw
directory under `data/support/` with a `README.txt` that says the same, and
exits non-zero. A sweep that could not run is not a sweep that found nothing.

```sh
nufi-box support --to /Volumes/USB   # write it somewhere other than data/support/
```

## Backups

```sh
nufi-box backup                       # into data/backup/<timestamp>/
nufi-box backup --to /Volumes/USB     # or onto a disk you carry away
nufi-box backup --install-nightly --at 03:30
nufi-box restore data/backup/20260914-033000
```

`nufi-box status` says when the last one was, or that there has never been one.

**What it holds, and why each piece is there.** Two database dumps look like a
complete backup right up to the moment somebody tries to bring a box back from
them, so the backup is decided by what a restore needs:

| | |
|---|---|
| `postgres.sql.gz` | `pg_dumpall` — the app, Studio and LiteLLM databases, and the roles |
| `mongodb.archive.gz` | the app's own data: accounts, conversations, agents |
| `drives.tar.gz` | **the department's documents** — the one thing on the box nobody else has a copy of. `_routines/` is left out: the box can write those reports again. |
| `app-uploads.tar.gz` | files people attached in the app |
| `caddy-data.tar.gz` | **the certificate authority itself.** `data/nufi-box-ca.crt` is only the copy handed to laptops; the root key lives in this volume. Restore without it and the box comes back up perfectly, serving a certificate every laptop that was told to trust it now rejects. |
| `ingest-state.tar.gz` | what the watcher has already uploaded. Without it, every document on every drive goes up again and each agent ends up holding two of everything. |
| `ca.tar.gz`, `env` | the published certificate, and the secrets all of the above are keyed to |

**A backup holds the box's secrets in clear.** `env` is the box's `.env` —
database passwords, JWT secrets, the LiteLLM master key. The directory is
`0700` and the file `0600`, and a copy on a USB disk in a drawer is the box's
keys in a drawer. Treat it the way you would treat the box.

**Retention.** The newest seven are kept and older ones pruned (`--keep N`), so
a box cannot fill its own disk with its own backups. Only the timestamped
directories this command writes are ever considered for pruning.

**Nightly** installs a launchd job (macOS) or a systemd user timer (Linux), not
a container. A container that could back the box up would need the docker
socket, which is the whole host handed to anything that gets into that
container. `--remove-nightly` takes it away again.

**Restoring** puts `.env` and the certificate authority back *before* it starts
anything: data restored into a stack already running on freshly generated
secrets is a restore that half-works — the rows come back and the sessions,
signed tokens and certificate do not match them. It asks you to type the box's
name first, unless you pass `--yes`. Afterwards, `nufi-box doctor`.

It **replaces** rather than merges. The drive tree is swapped, not extracted
over — `tar -xzf` writes what is in the archive and removes nothing, so a file
added since the backup would otherwise survive the one operation meant to undo
it. The tree as it was is kept in `data/drives.previous`, so a restore from the
wrong backup is not the end of the department's documents. The database dump is
taken with `pg_dumpall --clean`, so it drops each database before recreating it.

Two errors during a restore are expected and harmless:

```
ERROR:  current user cannot be dropped
ERROR:  role "nufi" already exists
```

The dump tries to drop the role it is being restored as. Anything else — in
particular `relation ... already exists` — means the databases were not dropped
and you are looking at a merge, not a restore.

One limit worth knowing: `mongorestore --drop` drops the collections that are
*in the archive*. A collection created since the backup and absent from it
survives.

### Running them on a clock

A routine can also run on a schedule and leave its answer on the department's
drive. `data/schedules.ini` holds one section per scheduled routine, and the
installer ships it with every section commented out — nothing runs until you
uncomment one.

```ini
[legal-weekly]
cron  = 0 17 * * 5
flow  = Routine · weekly report from the drive
drive = legal
ask   = 이번 주 주간보고 초안을 써줘.
out   = weekly-report-{date}.md
```

```sh
nufi-box schedule list      # what that file means, and when each next fires
nufi-box logs nufi-cron     # what happened when one ran
```

The answer lands in `data/drives/legal/_routines/weekly-report-2026-09-18.md`,
inside the department's own shared folder. **Nothing under `_routines/` is ever
embedded**: without that rule last week's report becomes a source this week's is
drafted from, and the routine ends up citing itself. That is not hypothetical —
it was watched happening on this box before the rule existed.

A run that outstays `NUFI_CRON_RUN_TIMEOUT` (15 minutes by default) is
**cancelled at Studio**, not merely abandoned: an abandoned run keeps generating
and holds the box's one model against every other question. A schedule that is
still running when its next turn comes round is skipped. Nothing is caught up —
a box that was off over a scheduled minute has missed that report, and firing
five hours of them at boot is worse than the gap.

Details and the reasoning:
[`deploy/platform/adapters/nufi-cron/README.md`](../platform/adapters/nufi-cron/README.md).

### …or when a file lands

A routine can also fire from a folder instead of a clock — a new hire's file
dropped into `onboarding/new/` in HR's drive, and an HR policy routine
answers from that drive with the file's name in the question. The routine
itself is unchanged: `watch` only decides *when* it runs, the same flow
still just answers the `ask` from the `drive`, citing a policy file or
saying plainly when the policy is silent. A section has **exactly one**
trigger: `cron` or `watch`, never both, never neither — a section with
either mistake is reported and dropped like any other typo in this file.

```ini
[hr-onboarding]
watch = onboarding/new
flow  = Routine · HR helpdesk from the policy
drive = hr
ask   = onboarding/new/{file} 에 새 입사자의 서류가 들어왔습니다. 규정에 따르면 신규 입사자에게 안내해야 할 절차를 알려줘.
out   = onboarding-{file}-{date}.md
```

`watch` is a folder relative to the drive — `onboarding/new`, not
`/onboarding/new` or `../onboarding/new`, and never under `_routines/`
itself — and it names ONE folder, not a tree: a file inside a subfolder of
it never fires (two files of the same name in different subfolders would
otherwise collide on the same `{file}` and the same `out`). `{file}` fills
in the file that triggered the run: its full name, extension included, in
`ask` (so the question above reads "... `kim-minsu.pdf` 에 ..."); its bare
name without the extension in `out` (so the answer lands as
`onboarding-kim-minsu-2026-09-18.md`).

Two rules keep a watched folder from misfiring:

- **A file has to sit still for two ticks in a row** — same size, same
  modified time — before it fires. A copy still in progress, or a Samba
  write still landing, must not trigger a routine against a half-written
  file. At the default 20-second tick this means a landed file fires
  20–40 seconds after it stops changing — plus however long the run ahead of
  it in the queue takes, since the box answers one question at a time.
- **The first scan of a `watch` folder fires nothing.** Everything already
  there is recorded as seen, the same "nothing is caught up" rule a `cron`
  schedule follows — a folder with forty résumés in it already must not
  launch forty runs the moment the box comes up. Pointing `watch` (or
  `drive`) at a different folder is treated the same way: nothing already in
  the new folder fires either.

After a run — successful or not — the file is marked seen and will not fire
again on its own; a broken flow does not get retried every twenty seconds.
Editing the file afterwards (a new modified time) makes it eligible again,
which is what a person expects. Hidden files, Office/Samba temp files
(`~$…`, `~WRD….tmp`, `.~lock…`), a download still in flight
(`.tmp`/`.part`/`.crdownload`/`.partial`), and `Thumbs.db`/`desktop.ini` are
never watched. A `watch` folder that does not exist yet is not an error — it
is logged once, and picked up as soon as someone creates it on the share
(even a file dropped in the very same moment the folder is).

### Works sandboxes and where they may reach

A NUFI Works sandbox — the container an agent's code runs in — lives on the
`works-sandbox` network, which has no route out (the network itself is
`internal: true`, not a firewall rule that could be missed). The only exit is
`works-egress`, a proxy that consults an allow list and refuses everything
else with a 403. It logs every refusal to stdout — there is no log file to go
looking for — one line per attempt, by hostname:

```sh
nufi-box logs works-egress
# Proxying refused on filtered domain "evil.example"
```

Two hosts are always allowed and are not yours to remove: `works` (the Works
server the sandbox reports back to) and `litellm-proxy` (the gateway the
model is reached through). Everything else comes from `.env`:

```
WORKS_EGRESS_ALLOW=pypi.org,files.pythonhosted.org
```

Bare hostnames, comma-separated. A scheme, a path, a port, a glob or an
address is refused at start with the entry named, and so is the model host
by the names the box knows it under (including the box's own name, which
serves the model directly on an ollama-profile box) — a sandbox reaches the
model through the gateway or not at all, which keeps every model call inside
the same limits and guardrails as a chat.

If the proxy is down, sandboxes have no network rather than an unfiltered
one — that falls out of `works-egress` being the sandbox network's only
member with a route out, not from anything doctor does. `nufi-box doctor`
asks the proxy, from inside the sandbox network, for a host that is not on
the list and expects the 403 — the one answer that proves the filter is
loaded, since a proxy that lets everything through looks healthy by every
other measure.

Nothing here runs an agent yet: the sandboxes themselves arrive with the next
piece, which installs the provider and registers the environment.

### NUFI Works on the box

`install-box.sh --with-works` (Ubuntu only) adds NUFI Works at
`https://<box>:3003`, entered from the Agents page like Studio. Every agent
run on it lands in a **gVisor** sandbox: a container under the `runsc`
runtime the installer registers, on the `works-sandbox` network, with no
route out except the egress proxy above. The box registers this itself —
`nufi-box works install` signs in as the box admin through the console,
claims the instance, installs the sandbox provider, registers the
environment pinned to the image the installer pulled, makes it the default
and archives the upstream `Local` environment (which would have run agent
code inside the Works container under plain Docker).

Two things to know:

- **The Works container holds the Docker socket.** That is how it creates
  sandboxes as sibling containers, and it is the only service that has it.
  Whoever can run code *in the Works container* can start containers on the
  box as root; nothing in a sandbox can.
- **A sandbox's model key is a LiteLLM virtual key** (`WORKS_MODEL_KEY`),
  never the master key: the key reaches the sandbox, and the gateway is on
  the allow list.

`nufi-box doctor` checks the runtime, the server and the registration.
`nufi-box works status` asks Works whether the registration still holds; run
`nufi-box works install` again after an upgrade. A LiteLLM key that was
revoked in the console is not noticed by the box — delete `WORKS_MODEL_KEY`
from `.env` and run `nufi-box works install` again to mint a new one. Hiring
a coding agent (codex, claude, opencode) is meant to work as in the cloud —
not yet exercised on a live box; a NuFi knowledge agent needs its
`gatewayUrl` set to `http://litellm-proxy:4000/v1` and a model the box
serves. `WORKS_BOX_KEY` in `.env` is the box admin's own Works API key
(instance admin), kept at 0600 beside the other secrets; the LiteLLM virtual
key it mints for a sandbox carries no budget of its own — the box's usage
limits apply through the gateway's own policy.

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
| `mesh up` / `mesh status` / `mesh down` | Join this box to the coordinator so it can be reached from home, show where it is on the mesh, or leave |
| `invite <name> [--os win\|mac\|linux] [--drives a,b]` | Write a one-file join for a new laptop — see [From home](#8-from-home) |
| `members` | List the laptops currently joined to the mesh |
| `revoke <name>` / `revoke --id <id>` | Remove a laptop's access to the mesh |
| `flows install` | Put the department routines into Studio — safe to repeat |
| `flows list` | Every flow in the box's Studio, with its id |
| `update [--ref REF] [--yes]` / `update --rollback` | Fetch the newest release, apply it, check it, roll back automatically if the check — or the apply, or the installer — fails — see [Updating](#updating) |
| `backup [--to DIR] [--keep N]` / `restore DIR` | Dump the databases, drives and secrets, or put a backup back — see [Backups](#backups) |
| `support [--to DIR]` | Gather a diagnostics bundle (no secret in it) to send to support@nufi.me — see [When something is wrong](#when-something-is-wrong) |

### Updating

```bash
nufi-box update                       # fetch the newest main, apply, check
nufi-box update --ref nufi-box-v1.2.0 # a specific tag instead of main
nufi-box update --rollback            # put back what the last update replaced
```

`update` asks for confirmation (type the box name) unless run with `--yes` —
needed for anything without a terminal (a script, a timer, once one exists).
It resolves the ref (or `main`) to a commit through the GitHub API first, so
the fetched archive and the box's own report of what it updated to
(`nufi-box status`'s `update: <sha> since <date>`) name the same commit; if
the API is unreachable it falls back to fetching the ref directly and says
`sha unknown`. `NUFI_BOX_SOURCE` in `.env` overrides the fetch entirely (a
mirror for a box that cannot reach GitHub for the tarball either) and skips
the resolve.

One command re-runs the whole day-one path: it fetches the whole archive
(the archive is the whole repository — pulling `deploy/box` out of it
selectively during extraction is a bsdtar (macOS) feature; GNU tar, what
Ubuntu actually ships, needs literal member names and fails plainly on a
glob, so this takes the whole archive rather than being right on one
platform and wrong on the other), runs `nufi-box backup` first, snapshots the current
files, the routine builder and adapter, and the digest of every image
running now to `.previous/`, applies the new `deploy/box` and the two
directories beside it (the same three described in [Boxes without GitHub
access](#boxes-without-github-access)), and re-runs `install-box.sh` — the
same installer day one used, so `.env`, every answer, and the mesh address
are kept exactly as `install-box.sh` already keeps them on any re-run.

It then runs `nufi-box doctor`. A pass is the whole result. A failure — the
health check, the installer, or the apply itself — rolls back automatically:
the files and the running images go back to what `.previous/` holds, the
stack restarts, and doctor runs once more so the message says whether the
box is healthy again. A rollback does **not** restore the backup taken at
the start on its own — an update's migrations are meant to carry the data
forward, and putting the database back is a decision for a person holding
the backup's path (`nufi-box restore <path>`), never something a failed
check decides by itself.

`nufi-box status` shows `update: <sha> since <date>` once a box has updated,
or `update: never updated` before the first one; a rollback clears it.

Needs `rsync`, which `install-box.sh` installs alongside Docker on Ubuntu.

**Not signed yet.** This is GitHub over TLS — the same transport a browser
gets — not a signed bundle. See [What is not built yet](#10-what-is-not-built-yet).

## 8. From home

A laptop on an LTE hotspot, at a hotel, or anywhere off the office LAN can
still reach the box — once it has joined the mesh coordinator (`nufi-box
mesh up` gives the box a stable mesh address and sets `BOX_MESH_HOST` in
`.env`; `invite` refuses with a clear message if that has not happened
yet).

Nothing about the box changes when it goes on the mesh: the same URLs, the
same certificate, the same drives, the same login. What changes is that the
box's name now resolves from anywhere its members are, instead of only on the
office LAN.

### Putting the box on the mesh

The coordinator (`deploy/coordinator`) is a small VPS running headscale. It
hands out one pre-auth key per machine and relays traffic when two machines
cannot reach each other directly. One coordinator serves every box and every
member; it holds no documents and no models, only the list of machines allowed
onto the mesh, which is why 1 GB of RAM is enough for it. Standing one up is
[its own runbook](../coordinator/README.md).

**Three values come off the coordinator**, and the box needs all three to be
fully useful:

| Value | Where it comes from | Without it |
|---|---|---|
| `MESH_SERVER_URL` | `https://<the coordinator's hostname>` | the box cannot join at all |
| `MESH_AUTH_KEY` | minted per box on the coordinator: `headscale preauthkeys create --user <id> --tags tag:box` — single use | the box cannot join at all |
| `MESH_API_KEY` | printed once by the coordinator's `./bootstrap.sh` | the box joins, but `invite` / `members` / `revoke` cannot call the coordinator |

Give the box its coordinator once, at install time:

```bash
./install-box.sh --yes \
  --mesh https://mesh.nufi.me \
  --auth-key tskey-auth-…            # the box's own key: tag:box, single use
  --mesh-api-key hskey-api-…         # optional, but `invite` needs it
```

or afterwards, by putting `MESH_SERVER_URL` and `MESH_AUTH_KEY` in `.env` and
running `nufi-box mesh up`. Either way the box:

- joins as node `${BOX_NAME}` (a `tailscale` container with the host's own
  network on Linux; the native Tailscale app on macOS, whose two commands
  `mesh up` prints for you),
- writes `BOX_MESH_IP` and `BOX_MESH_HOST` into `.env`,
- generates `caddy/mesh.caddy` so all six product ports answer on the mesh
  name with the same certificate laptops already trust, and reloads Caddy
  (the plain-HTTP landing page and the CA download need no entry there — that
  site has no host matcher, so it already answers on the mesh name).

```
$ nufi-box mesh status
  coordinator    https://mesh.nufi.me
  mesh address   100.64.0.2
  MagicDNS name  nufi.box.nufi.me
```

From home, use the **name**, not the mesh address: `https://nufi.box.nufi.me:3080`.
A browser that dials a bare IP sends no SNI, and the box has one certificate
to fall back on — the LAN one — so the mesh address alone will not validate.
The name always resolves for a joined laptop; that is what the mesh is for,
and it is what every join file uses.

The drives need nothing extra. Samba's port is published by Docker, which
binds every address the machine has, so `\\nufi.box.nufi.me\legal` works the
moment the box is on the mesh. (Do not "help" it by pinning smbd's
`interfaces` to the mesh address: Samba runs in a container that has neither
that address nor the LAN one, and it would stop answering on both.)

`nufi-box mesh down` takes the box off the mesh and removes the mesh sites
from Caddy; the box keeps its registration, so `mesh up` rejoins at the same
address without a new key. To remove a *laptop* for good, use `revoke`.

Once `MESH_SERVER_URL` is in `.env`, the mesh node is part of the stack every
other verb operates on: `nufi-box status` lists it, `nufi-box logs tailscale`
follows it, `nufi-box down` stops it along with the front door rather than
leaving it advertising a box that is no longer answering, and `nufi-box up`
brings it back.

A coordinator with a **public** certificate (the field configuration) needs
nothing else. A development coordinator running on its own internal CA does:
copy that coordinator's `data/coordinator-ca.crt` onto the box and point
`MESH_CA_FILE` in `.env` at it, or the box's `tailscale` container will not
trust the control server and `invite` will fail on
`unable to get local issuer certificate`.

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
node (the join file registers the laptop under `alice`, so the name really
does match); her laptop can no longer reach the box until invited again.
If two laptops ever share a name, `revoke` refuses to guess — it lists both
node ids and asks you to run `nufi-box revoke --id <id>` for the one you
mean.

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
| `nufi-box flows list` says `flows: no STUDIO_API_KEY in .env — run: nufi-box flows install`, or `run_flows.py` says `no Studio API key: pass --key or set $STUDIO_API_KEY` | Do what the first one says: `nufi-box flows install`. It mints the box's key, writes it back to `.env`, and leaves the routines that are already in Studio alone. The box arrives here when the install could not reach Studio at the routines step — that step warns rather than stopping, so the install finishes and the key is simply not there yet. The routines themselves are untouched; only the box's own way to call them is missing. A box that once had a working key does not lose it by re-running `./install-box.sh`: `STUDIO_API_KEY` is kept across a re-install like every other secret in `.env`. |
| After upgrading a box that is on a mesh, nothing answers on any port and `nufi-box logs caddy` repeats `Could not import … at /etc/caddy/caddy/mesh.caddy` | `caddy/mesh.caddy` is generated by `nufi-box mesh up` and is not part of the checkout, so an upgrade that changes the Caddyfile can leave a render behind that the new Caddyfile cannot read — and Caddy then refuses *every* site, LAN and mesh. `install-box.sh`, `nufi-box up` and `nufi-box restart` now put the file back in step before starting Caddy, so upgrading through them is enough; `nufi-box doctor` names it, and `nufi-box mesh up` fixes it on its own. |

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

## 10. What is not built yet

This install gives you a box on your own LAN, and — once it is on a
coordinator — reachable from anywhere its members are. The following are not
built yet:

- **A member on a network other than the box's.** The coordinator has run on
  a real VPS with a public name and a Let's Encrypt certificate, a box has
  joined it, and a member has signed in over the relay (the run is recorded in
  [the coordinator's runbook](../coordinator/README.md#10-what-has-been-proved-and-what-has-not)).
  Both test members sat on the same machine as the box, so a laptop on an LTE
  hotspot is the one measurement still to take.
- **A signed update bundle, an update timer, and a USB update path.**
  `nufi-box update` (see [Updating](#updating)) fetches straight from GitHub
  over TLS, checks the result, and rolls back automatically if it fails —
  but the archive is unsigned, nothing runs it on a schedule, and there is no
  offline path for a box with no network at all.
- **Dudaji reaching into your box.** `nufi-box support` (see [When something
  is wrong](#when-something-is-wrong)) is the local half only — it packages
  what the box already knows about itself into a file you send. It opens no
  connection from Dudaji into the box, and nothing on the box listens for
  one. Remote support access would be a separate, explicit decision — not
  something this command does on its own.
- **NUFI Works on macOS.** Works runs on the box on Ubuntu
  (`install-box.sh --with-works`, see [NUFI Works on the
  box](#nufi-works-on-the-box)); Docker Desktop cannot host the gVisor
  runtime it needs, so a Mac box does not get it.
- **A weekly report that knows which files are this week's.** `weekly` reads
  the whole drive and asks the model to respect the period; nothing filters
  the files by their modification date. See [Departments and
  drives](#5-departments-and-drives).
- **A cap on how much a routine generates.** Nothing bounds a routine's
  output, and nothing stops a run whose caller has gone — on a small model
  that means one abandoned routine can hold the model and slow the whole box.
  The setting belongs on the routine's model node and this Studio build does
  not expose it. The workaround, and how to spot it, are in [Departments and
  drives](#5-departments-and-drives).
- **Routines for members — now built.** A member signing in through the app is
  given their own copy of each of the four routines, on every sign-in, not only
  the first. A copy nobody has touched is refreshed from the box; a copy the
  member has edited is left alone for good. It needed a change in the Studio
  image, which shipped.
- **The acceptance score is a measurement of the model, not the box.** The
  10/32 figure above says how good `qwen2.5:7b` is at these questions. It
  does not say whether ingestion, retrieval, or citation work — those
  passed in full.
