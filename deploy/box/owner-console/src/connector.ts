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
// de-branded agent bundle FROM THE BOX (not tailscale.com) and installs+enrols
// it. Everything it interpolates (key, URL, CAs) comes from the verified invite
// token / box config, never member input; the member name is safeMember'd. The
// download uses the same origin the member reached /connect on (so it works on
// the box's LAN name or IP, over plain :80 before the CA is trusted).
function agentConnectorLinux(input: ConnectorInput): Connector {
  const member = safeMember(input.member);
  const boxUrl = (input.boxUrl ?? '').replace(/\/$/, '');
  const body = `#!/bin/bash
# NuFi box -- join for ${member}. Installs the NuFi agent from the box and joins.
# No Tailscale download: the de-branded client is served by the box itself.
set -e
echo "NuFi box -- joining as ${member}"
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
case "$ARCH" in x86_64|amd64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; *) echo "unsupported architecture: $ARCH"; exit 2;; esac
TMP="$(mktemp -d)"
echo "Downloading the NuFi agent..."
curl -fsSL "${boxUrl}/agent/nufibox-agent-linux-$ARCH.tar.gz" -o "$TMP/agent.tgz"
tar -xzf "$TMP/agent.tgz" -C "$TMP"
CA_ARG=""
CA_B64="${input.coordCaB64}"
if [ -n "$CA_B64" ]; then printf '%s' "$CA_B64" | base64 -d > "$TMP/coord-ca.crt"; CA_ARG="--ca $TMP/coord-ca.crt"; fi
echo "Installing and joining (you may be asked for your password)..."
sudo "$TMP/nufibox-agent/install.sh" enroll --server "${input.serverUrl}" --auth-key "${input.key}" $CA_ARG --hostname "${member}"
echo "Opening NuFi -- sign up (or sign in) to start chatting..."
xdg-open "https://${input.boxMeshHost}:3080/register" 2>/dev/null || echo "Open https://${input.boxMeshHost}:3080/register in your browser."
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
