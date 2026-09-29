import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// Renders the per-OS "connector" a member runs to join the box's mesh. It fills
// the SAME templates `nufi-box invite` uses (lib/join-templates/*, copied into
// this image) rather than duplicating them, so the two never drift.

export type OS = 'macos' | 'windows' | 'linux';
const EXT: Record<OS, string> = { macos: 'command', windows: 'cmd', linux: 'sh' };

export function isOS(v: unknown): v is OS {
  return v === 'macos' || v === 'windows' || v === 'linux';
}

export type ConnectorInput = {
  os: OS;
  member: string;
  key: string;
  serverUrl: string;
  boxMeshHost: string;
  departments: string[];
  boxCaB64: string; // base64 of the box's Caddy CA
  coordCaB64: string; // base64 of the coordinator CA, or '' for a public coordinator
  boxUrl?: string; // the origin the member reached the box on, for the agent download (linux)
  // SHA-256 (hex) of each agent tarball, baked at image-build time. Embedded in
  // the linux connector so it verifies the download before running it as root.
  // '' for an arch when the box could not read the digest — the check is then
  // skipped for that arch (the built image always ships both).
  agentSha256?: { amd64?: string; arm64?: string };
};

// A member name doubles as a Tailscale hostname and the download filename, so
// reduce it to a safe DNS-ish label.
export function safeMember(name: string): string {
  const s = (name || '')
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
  return s || 'member';
}

// POSIX single-quote: wrap in '' and escape any embedded quote, so a department
// name never breaks out into command substitution ($(), backticks) or word
// splitting in the generated mac/linux script.
const sq = (s: string) => `'${s.replace(/'/g, "'\\''")}'`;

// Escape a value that lands inside a double-quoted bash string. These come from
// the verified invite token / box env (not member input), so this is defence in
// depth for the "absolute security" bar: a stray " $ ` or \ must never break out
// of the quotes into a command that then runs as root via sudo.
const dq = (s: string) => s.replace(/(["\\$`])/g, '\\$1');

// Per-OS drive-mapping lines, mirroring lib/mesh.sh's mesh_drives_block: one
// `net use` / `open smb://` / `gio mount` per department. Windows letters count
// down from Z so they rarely collide with the laptop's own C:/D:. Department
// names are box-owner config (not member input), but they carry spaces and are
// quoted here so a name like "Human Resources" neither breaks the line nor
// evaluates as shell.
function driveLines(os: OS, host: string, departments: string[]): string {
  if (!host || departments.length === 0) return 'echo "No drives were configured for this invite."';
  const letters = 'ZYXWVUTSRQPONMLKJIHGFEDCBA';
  return departments
    .map((d, i) => {
      if (os === 'windows') {
        if (i >= 26) return `echo "Too many drives to letter automatically -- map \\\\${host}\\${d} by hand"`;
        return `net use ${letters[i]}: "\\\\${host}\\${d}" /persistent:yes`;
      }
      if (os === 'macos') return `open ${sq(`smb://${host}/${d}`)}`;
      return `gio mount ${sq(`smb://${host}/${d}`)} || echo "could not mount this drive automatically -- open smb://${host}/${d} from your file manager"`;
    })
    .join('\n');
}

export type Connector = { filename: string; contentType: string; body: string };

// Linux members get the NufiBox Agent flow: the connector downloads the
// de-branded agent bundle FROM THE BOX (not tailscale.com), trusts the box's CA
// (so the sign-up page opens without a cert warning), installs+enrols the agent,
// and maps the department drives — parity with the mac/Windows templates.
// Everything it interpolates (key, URL, CAs) comes from the verified invite
// token / box config, never member input; the member name is safeMember'd and
// the shell-context values are dq'd. The download uses the same origin the
// member reached /connect on (so it works on the box's LAN name or IP, over
// plain :80 before the CA is trusted).
function agentConnectorLinux(input: ConnectorInput): Connector {
  const member = safeMember(input.member);
  const boxUrl = dq((input.boxUrl ?? '').replace(/\/$/, ''));
  const serverUrl = dq(input.serverUrl);
  const key = dq(input.key);
  const meshHost = dq(input.boxMeshHost);
  const drives = driveLines('linux', input.boxMeshHost, input.departments);
  // Digests are hex ([0-9a-f]) — safe inside "…" as-is; '' when unknown.
  const shaAmd64 = input.agentSha256?.amd64 ?? '';
  const shaArm64 = input.agentSha256?.arm64 ?? '';
  // boxCaB64 / coordCaB64 are base64 ([A-Za-z0-9+/=]) — safe inside "…" as-is.
  const body = `#!/bin/bash
# NuFi box -- join for ${member}. Installs the NuFi agent from the box and joins.
# No Tailscale download: the de-branded client is served by the box itself.
set -e
echo "NuFi box -- joining as ${member}"
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
case "$ARCH" in x86_64|amd64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; *) echo "unsupported architecture: $ARCH"; exit 2;; esac
TMP="$(mktemp -d)"
echo "Downloading the NuFi agent..."
curl -fsS "${boxUrl}/agent/nufibox-agent-linux-$ARCH.tar.gz" -o "$TMP/agent.tgz"
# Verify the download against the digest the box baked in at build time, BEFORE
# we run anything from it as root. Defence in depth for the box-CA-trusted
# delivery path: a tampered tarball is refused rather than installed.
case "$ARCH" in amd64) WANT_SHA="${shaAmd64}";; arm64) WANT_SHA="${shaArm64}";; *) WANT_SHA="";; esac
if [ -n "$WANT_SHA" ]; then
  GOT_SHA="$(sha256sum "$TMP/agent.tgz" | awk '{print $1}')"
  if [ "$GOT_SHA" != "$WANT_SHA" ]; then
    echo "SECURITY: the NuFi agent download failed its integrity check -- refusing to install. Ask the box owner for a fresh invite." >&2
    exit 3
  fi
fi
tar -xzf "$TMP/agent.tgz" -C "$TMP"
BOX_CA_B64="${input.boxCaB64}"
if [ -n "$BOX_CA_B64" ]; then
  echo "Trusting the box's certificate (you may be asked for your password)..."
  printf '%s' "$BOX_CA_B64" | base64 -d | sudo tee /usr/local/share/ca-certificates/nufi-box.crt >/dev/null
  sudo update-ca-certificates >/dev/null
fi
CA_ARG=""
CA_B64="${input.coordCaB64}"
if [ -n "$CA_B64" ]; then printf '%s' "$CA_B64" | base64 -d > "$TMP/coord-ca.crt"; CA_ARG="--ca $TMP/coord-ca.crt"; fi
echo "Installing and joining (you may be asked for your password)..."
sudo "$TMP/nufibox-agent/install.sh" enroll --server "${serverUrl}" --auth-key "${key}" $CA_ARG --hostname "${member}"
echo "Mapping your department drives (best effort)..."
${drives}
echo "Opening NuFi -- sign up (or sign in) to start chatting..."
xdg-open "https://${meshHost}:3080/register" 2>/dev/null || echo "Open https://${meshHost}:3080/register in your browser."
`;
  return { filename: `nufi-join-${member}.sh`, contentType: 'application/x-shellscript', body };
}

export function renderConnector(input: ConnectorInput, templatesDir: string): Connector {
  if (input.os === 'linux') return agentConnectorLinux(input);
  const member = safeMember(input.member);
  const template = readFileSync(join(templatesDir, `${input.os}.${EXT[input.os]}`), 'utf8');
  const subs: Record<string, string> = {
    MEMBER: member,
    AUTH_KEY: input.key,
    MESH_SERVER_URL: input.serverUrl,
    BOX_MESH_HOST: input.boxMeshHost,
    CA_B64: input.boxCaB64,
    COORD_CA_B64: input.coordCaB64,
    DRIVES: driveLines(input.os, input.boxMeshHost, input.departments),
  };
  let body = template;
  for (const [k, v] of Object.entries(subs)) body = body.split(`@${k}@`).join(v);
  return {
    filename: `nufi-join-${member}.${EXT[input.os]}`,
    contentType: input.os === 'windows' ? 'application/octet-stream' : 'application/x-shellscript',
    body,
  };
}
