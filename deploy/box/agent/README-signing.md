# Signing the macOS NufiBox Agent

The `.github/workflows/agent-macos.yml` workflow builds the de-branded agent for
macOS and produces a **signed + notarized** universal `.pkg` — so a member's Mac
installs it with no Gatekeeper warning.

Signing and notarization happen **once, at build time**, with the Dudaji
Developer ID. The signed artifact is the same for every box and every customer:
customers never need their own Apple certificate. The stapled notarization
ticket verifies **offline**, so an air-gapped box can serve the pkg to an
air-gapped Mac.

## One-time: add six repository secrets

The workflow needs these under **Settings → Secrets and variables → Actions**.

### Signing certificates (two `.p12` + their password)

Export both Developer ID identities from the Mac that has them (Keychain
Access → **My Certificates** → select the identity → right-click → **Export…**
→ `.p12`, set an export password — use the *same* password for both):

- `APPLE_DEV_ID_APP_P12` — base64 of the exported **"Developer ID Application: Dudaji Vn"** `.p12`
- `APPLE_DEV_ID_INSTALLER_P12` — base64 of the exported **"Developer ID Installer: Dudaji Vn"** `.p12`
- `APPLE_P12_PASSWORD` — the export password you set

Base64 a file for pasting into a secret:

```bash
base64 -i DeveloperID_Application.p12 | pbcopy   # then paste as APPLE_DEV_ID_APP_P12
base64 -i DeveloperID_Installer.p12   | pbcopy   # then paste as APPLE_DEV_ID_INSTALLER_P12
```

### Notarization (an App Store Connect API key)

Preferred over an Apple-ID app-specific password for CI: it is team-scoped and
revocable, with no personal Apple ID. Create it at
**appstoreconnect.apple.com → Users and Access → Integrations → App Store
Connect API → Team Keys → +** (role **Developer** is enough). Download the
`.p8` (once only), and note the Key ID and Issuer ID.

- `APPLE_NOTARY_KEY_P8` — base64 of the `.p8` (`base64 -i AuthKey_XXXX.p8 | pbcopy`)
- `APPLE_NOTARY_KEY_ID` — the key's **Key ID**
- `APPLE_NOTARY_ISSUER_ID` — the **Issuer ID** (a UUID at the top of the Keys page)

## Run it

- **Manually:** Actions → **agent-macos** → *Run workflow* (optionally set the
  tailscale engine version, default `1.102.3`).
- **By tag:** push a tag `agent-macos-v<version>`.

Either way the workflow builds, signs, notarizes, staples, uploads a build
artifact, and publishes the `.pkg` + its `.sha256` to a release tagged
`agent-macos-v<version>`. The box image (D2) fetches that release asset the way
`build-agent.sh` fetches the Linux engine — at image-build time, verified by the
published sha256.

macOS runners are metered (~10× minutes) and notarization is slow, so this runs
only on demand or on a tag, never on every commit.

## Local builds

The same script runs locally on a Mac that has the identities in its keychain
and a stored notarytool profile:

```bash
deploy/box/agent/build-agent-macos.sh              # sign + notarize + staple
NOTARIZE=0 deploy/box/agent/build-agent-macos.sh   # sign only
```

Local notarization uses the keychain profile `NOTARY_PROFILE` (default
`nufibox-notary`, created once with `xcrun notarytool store-credentials`); CI
passes `NOTARY_KEY` / `NOTARY_KEY_ID` / `NOTARY_ISSUER` instead.
