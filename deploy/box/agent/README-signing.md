# Signing the macOS NufiBox Agent

The `.github/workflows/agent-macos.yml` workflow builds the de-branded agent for
macOS and produces a **signed + notarized** universal `.pkg` — so a member's Mac
installs it with no Gatekeeper warning.

It runs on a **self-hosted macOS runner** (Dudaji's signing Mac). The Developer
ID signing keys stay in that machine's keychain and are used in place — **never
exported to a CI secret, never uploaded anywhere.** This is the most secure
option and the one this repo is set up for.

Signing and notarization happen **once, at build time**, with the Dudaji
Developer ID. The signed artifact is the same for every box and every customer:
customers never need their own Apple certificate. The stapled notarization
ticket verifies **offline**, so an air-gapped box can serve the pkg to an
air-gapped Mac.

## One-time: prepare the signing Mac

The signing Mac must already have (this repo's dev Mac does):

- The **Developer ID Application** and **Developer ID Installer** identities for
  the team in its keychain (verify: `security find-identity -v | grep "Dudaji"`).
- A stored notarytool profile named **`nufibox-notary`** (create once with
  `xcrun notarytool store-credentials nufibox-notary --apple-id <id> --team-id
  <team> --password <app-specific-pw>`; see [[apple-signing-setup]] in memory).
- Go (`brew install go`) and the GitHub CLI (`gh`) on `PATH`
  (`/opt/homebrew/bin`), and the Xcode command-line tools with the licence
  accepted.

### Register it as a self-hosted runner

**GitHub → repo Settings → Actions → Runners → New self-hosted runner → macOS**,
then run the commands it shows. **Start the runner in your GUI login session:**

```bash
./run.sh          # NOT `svc.sh install` (a background LaunchDaemon can't reach
                  # an unlocked login keychain, so signing would fail)
```

Keep it scoped to this repository. **Never** add a `pull_request:` trigger to
this workflow — untrusted PR code must not run on a machine that holds signing
keys. The workflow triggers on manual dispatch or an `agent-macos-v*` tag only.

## Run it

- **Manually:** Actions → **agent-macos** → *Run workflow* (optionally set the
  tailscale engine version, default `1.102.3`).
- **By tag:** push a tag `agent-macos-v<version>`.

The runner builds, signs, notarizes, staples, uploads a build artifact, and
publishes the `.pkg` + its `.sha256` to a release tagged `agent-macos-v<version>`.
The box image (D2) fetches that release asset the way `build-agent.sh` fetches
the Linux engine — at image-build time, verified by the published sha256.

## Local builds

The same script runs by hand on the signing Mac:

```bash
deploy/box/agent/build-agent-macos.sh              # sign + notarize + staple
NOTARIZE=0 deploy/box/agent/build-agent-macos.sh   # sign only
```

It signs with the Developer ID identities in the keychain and notarizes with the
`NOTARY_PROFILE` keychain profile (default `nufibox-notary`).

## If you ever move to a GitHub-hosted runner instead

You would need exportable `.p12` files for both Developer ID identities plus an
App Store Connect API key, added as repository secrets, and the workflow would
import them into a temporary keychain. That path was set aside because the
identities on the current signing Mac are not cleanly exportable and Developer ID
certificates are limited (Apple refuses a second without revoking the first).
Self-hosted avoids all of that and keeps the keys off GitHub.
