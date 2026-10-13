# Member onboarding: separate the agent download from the join

Design note for splitting member onboarding into two independent parts — a
public **agent install** and a credential-only **join** — so onboarding no
longer depends on the box being reachable at install time.

## The problem

The de-branded join file merged two steps into one script: it downloads the
NuFi agent **from the box** and then enrolls.

```sh
# connector.ts (today): "Installs the NuFi agent from the box and joins."
curl -fsS "${boxUrl}/agent/nufibox-agent-linux-$ARCH.tar.gz" -o "$TMP/agent.tgz"
...
sudo "$TMP/nufibox-agent/install.sh" enroll --server "${serverUrl}" --auth-key "${key}" ...
```

`boxUrl` is `BOX_IP` (owner-console `memberBase`) or the origin the member
reached `/connect` on. So the download needs the box reachable at the right
address *before* the member has joined anything. In the field this broke every
way it could:

- `BOX_IP` resolved to a Docker bridge address (`172.17.239.144`) — in the join
  file, reachable from no other machine (`curl: (7) Failed to connect`).
- A WSL2 box sits behind the Windows host's NAT; its ports are not on the LAN
  without mirrored networking, and mirrored networking then collides with
  Windows' own SMB on port 445.
- It requires the member to be on the same network as the box.

The **old** model — official Tailscale downloaded from `tailscale.com` — had
none of these: the agent came from a public source, so only the **coordinator**
(public) had to be reachable. The de-branding (serving the agent from the box)
is what introduced the coupling.

## The goal

Separate the two concerns, the same shape on macOS, Linux and Windows:

1. **Agent install** — downloaded from a **public** location (GitHub Releases),
   independent of the box.
2. **Join** — one copy-paste `enroll` command carrying the invite's single-use
   pre-auth key and the coordinator URL.

A member on any network onboards with only the **coordinator** reachable (which
is its whole job); the box needs no reachability at install time. After joining,
the member reaches the box **over the mesh** by its mesh name, as today.

This is how mature clients already work: install the app from a public source,
then `up --authkey=…`.

## The two parts

**Download (public, per OS):** the agent installer as a GitHub Release asset
(the repo is public, so the download URLs are public and CDN-backed):

| OS | Asset | State |
|---|---|---|
| macOS | `nufibox-agent-macos.pkg` | already published by `agent-macos.yml` |
| Linux | `nufibox-agent-linux-<arch>.tar.gz` | NEW — publish from the existing cross-compile (`build-agent.sh`); a normal runner, no signing |
| Windows | `nufibox-agent-windows-<arch>.msi` | de-branded + signed — see the Windows-agent plan; official Tailscale as the interim |

**Enroll (the credential):** one command the member pastes:

```
# macOS / Linux
sudo nufibox-agent enroll --server <coordinator> --auth-key <key> [--ca <box-ca>] --hostname <name>
# Windows (de-branded)
nufibox-agent.ps1 enroll -Server <coordinator> -AuthKey <key> [-Ca <box-ca>] -Hostname <name>
# Windows (official-Tailscale interim)
tailscale up --login-server=<coordinator> --authkey=<key> --hostname=<name>
```

The key is single-use and expires in an hour; `/connect` mints it per invite.

## The `/connect` page

Two explicit steps, the macOS flow extended to every OS:

1. **Download for <OS>** → the public Release URL for that OS/arch.
2. **Copy this command** → the enroll command, with the invite's key filled in.

Reached through the invite share-link (token → the enroll command). No sign-in;
the invite token is the credential.

## Changes

- **`.github/workflows/agent-linux.yml`** (new): publish `nufibox-agent-linux-<arch>.tar.gz`
  + `.sha256` to a `agent-linux-v*` Release. Linux cross-compiles with CGO off,
  so this runs on a normal `ubuntu-latest` runner — no self-hosted runner and no
  signing (unlike macOS/Windows, which need their signing machines).
- **`owner-console/src/connector.ts`**: point the agent-download URL at the
  **public Release**, not `${boxUrl}/agent/…`; keep `${boxUrl}/agent/…` as the
  air-gap fallback. Split the generated artifact into a download step and an
  enroll command. Keep the integrity check — verify the download against the
  Release's published `.sha256`, as today it verifies a box-baked digest.
- **`owner-console/src/app.ts`** (the `/connect` HTML): the two-step UI per OS.
- **`lib/join-templates/*`**: adopt the same split, or retire in favour of the
  `/connect` two-step (see decisions).
- **`apps/docs/content/docs/box/members.mdx` / `reaching.mdx`**: the public
  download link + the enroll steps, per OS.
- **Windows**: the de-branded agent ships via its own plan (`deploy/box/agent`,
  `build-agent-windows.sh`, a `agent-windows.yml` sibling of `agent-macos.yml`);
  until it does, the Windows branch keeps the official-Tailscale command.

## Air-gap / offline boxes

The box keeps serving `/agent/…` (baked into the owner-console image). A member
with no route to GitHub (an air-gapped site) uses the box URL instead. So:
**public Release by default, the box URL as the fallback** — either chosen
automatically (try public, fall back to the box) or by an explicit offline
invite variant.

## What it fixes

- Wrong `BOX_IP` / `172.17.x` in join files — nothing downloads from the box.
- WSL2 NAT and the port-445 mirrored-mode collision — the box needs no
  LAN-reachability, so no mirrored networking is needed.
- The "same network" requirement — the member reaches only the public
  coordinator.

## Acceptance

- A member on a **different network** from the box: download the agent from the
  public Release URL, paste the enroll command → joins the coordinator → reaches
  the box by its mesh name (`https://<box>.<domain>:3080/health` → 200). The box
  was never contacted to install.
- **Air-gap**: a box with no internet; a member on the box LAN uses the box
  `/agent/` URL → same result.
- **Integrity**: a tampered agent download is refused (sha256 mismatch).

## Decisions to confirm

1. Keep the single-file join (`nufi-join-<name>.sh/.command/.cmd`) alongside the
   `/connect` two-step, or move to `/connect` only?
2. Air-gap fallback: automatic (try public, fall back to the box URL) or an
   explicit `--offline` invite that points at the box?
3. Windows target is the de-branded signed `.msi` (its own plan), with the
   official-Tailscale command as the interim — confirmed.
