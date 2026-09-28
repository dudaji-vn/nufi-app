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

export function renderConnector(input: ConnectorInput, templatesDir: string): Connector {
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
