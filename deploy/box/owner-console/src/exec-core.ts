// Pure exec allowlist: no fs, no spawn. Single source of truth shared by the
// console (src/exec.ts) and the owner-exec sidecar.
export const SERVICES = ['librechat', 'litellm-proxy', 'rag_api', 'ollama', 'caddy', 'mongodb', 'postgres', 'studio'] as const;
export const READ_CMDS = ['status', 'logs', 'doctor', 'support'] as const;
export const ACTIONS = ['start', 'restart', 'stop'] as const;

export type Action = (typeof ACTIONS)[number];

export class BadRequest extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BadRequest';
  }
}

export const COMPOSE = ['docker', 'compose', '-p', 'nufi-box'] as const;

export const isIn = <T extends readonly string[]>(set: T, v: unknown): v is T[number] =>
  typeof v === 'string' && set.includes(v);

export function auditLine(now: Date, what: string, service?: string): string {
  return [now.toISOString(), what, ...(service ? [service] : [])].join(' · ');
}

export function buildControlArgv(action: string, service: string): string[] {
  if (!isIn(ACTIONS, action)) throw new BadRequest('invalid action');
  if (!isIn(SERVICES, service)) throw new BadRequest('invalid service');
  return [...COMPOSE, action, service];
}

// Whole-box control: no service, acts on every container in the compose project.
export function buildBoxArgv(action: string): string[] {
  if (!isIn(ACTIONS, action)) throw new BadRequest('invalid action');
  return [...COMPOSE, action];
}

// The console control-plane: kept running on a whole-box STOP/RESTART so the
// Start/Restart buttons still work — a web-triggered stop must not take down the
// very web UI that turns it back on (caddy serves the console; owner-exec runs
// the commands). START brings everything, including these, back.
export const CONSOLE_PLANE = ['nufi-box-caddy-1', 'nufi-box-owner-console-1', 'nufi-box-owner-exec-1'] as const;

// List the box project's container NAMES (all, or only running). Robust to
// which compose overlays are loaded — unlike `docker compose`, which needs the
// matching COMPOSE_FILE to even name an overlay service like tailscale.
export function buildListContainersArgv(onlyRunning: boolean): string[] {
  const argv = ['docker', 'ps'];
  if (!onlyRunning) argv.push('-a');
  return [...argv, '--filter', 'label=com.docker.compose.project=nufi-box', '--format', '{{.Names}}'];
}

const CONTAINER_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9_.-]*$/;

// A whole-box action over container NAMES (from buildListContainersArgv).
// stop/restart skip the console plane so the UI survives; start touches all
// (already-running ones no-op). Names are validated; the list may be empty
// (caller no-ops).
export function buildBoxContainerArgv(action: string, names: string[]): string[] {
  if (!isIn(ACTIONS, action)) throw new BadRequest('invalid action');
  const keep = new Set<string>(CONSOLE_PLANE);
  const picked = names
    .map((n) => n.trim())
    .filter((n) => CONTAINER_NAME_RE.test(n))
    .filter((n) => (action === 'start' ? true : !keep.has(n)));
  return ['docker', action, ...picked];
}

export const BOX_SERVICE = '__box__';

// "Allow remote work" = the box's mesh connection, which is the tailscale
// container. Toggling it start/stops that ONE container by name (not a compose
// op, so it needs no mesh-overlay COMPOSE_FILE and works on any box). Stopping
// it takes the box off the mesh (LAN-only); starting it rejoins with the same
// registration. The full `nufi-box mesh up/down` (which also rewrites .env +
// caddy) stays a host command by design — this is the connectivity toggle only.
export const REMOTE_WORK_CONTAINER = 'nufi-box-tailscale-1';

export function buildRemoteWorkArgv(on: boolean): string[] {
  if (typeof on !== 'boolean') throw new BadRequest('remote-work needs a boolean');
  return ['docker', on ? 'start' : 'stop', REMOTE_WORK_CONTAINER];
}

// Whether the mesh (tailscale) container is actually running — the toggle's
// true state, which .env (BOX_MESH_IP) does NOT reflect after a stop/start.
// Prints `true`/`false`, or errors (non-zero) if the container does not exist.
export function buildRemoteWorkStatusArgv(): string[] {
  return ['docker', 'inspect', '-f', '{{.State.Running}}', REMOTE_WORK_CONTAINER];
}

const LOGS = [...COMPOSE, 'logs', '--no-color', '--tail=200'];

export function buildReadArgv(cmd: string): string[] | null {
  if (typeof cmd === 'string' && cmd.startsWith('logs ')) {
    const svc = cmd.slice(5);
    if (!isIn(SERVICES, svc)) throw new BadRequest('invalid command');
    return [...LOGS, svc];
  }
  if (!isIn(READ_CMDS, cmd)) throw new BadRequest('invalid command');
  switch (cmd) {
    case 'status':
      return [...COMPOSE, 'ps'];
    case 'logs':
      return [...LOGS];
    default:
      return null; // doctor / support: informational only, never executed
  }
}

// --- live box config (Config modal) ------------------------------------------
// The one box setting the owner can change from the UI and have applied live:
// which model endpoint the box talks to (AI Base Location + Model Name). It is
// edited in litellm/config.yaml — the one box config file that is NOT .env, so
// a container may be given write access to it without ever touching the box's
// secrets (.env, which holds every key/password, is mounted into NOTHING, by
// design). Other knobs (sign-up, departments, …) live only in .env and so are
// not live-editable from the UI; they stay a host-side change.
//
// exec-core owns the validation + the pure YAML read/write so the console, the
// sidecar and the tests share one source of truth; the privileged file write
// and the litellm recreate happen in the sidecar.
export const RECONFIGURE_SERVICES = ['litellm-proxy'] as const;

export type ConfigView = {
  aiBaseUrl: string;
  aiModel: string;
};

export type ConfigPatch = {
  aiBaseUrl: string;
  aiModel: string;
};

// http(s), no whitespace or quotes (it lands unquoted in the YAML).
const URL_RE = /^https?:\/\/[^\s'"]+$/;
// model ids like `qwen2.5:7b`, `llama-3-70b-instruct`, `openai/gpt-4o-mini`.
const MODEL_RE = /^[A-Za-z0-9._:/-]{1,128}$/;

export function validateConfigPatch(input: unknown): ConfigPatch {
  const o = (input && typeof input === 'object' ? input : {}) as Record<string, unknown>;
  const aiBaseUrl = typeof o.aiBaseUrl === 'string' ? o.aiBaseUrl.trim() : '';
  const aiModel = typeof o.aiModel === 'string' ? o.aiModel.trim() : '';
  if (!URL_RE.test(aiBaseUrl)) throw new BadRequest('AI Base Location must be an http(s) URL');
  if (!MODEL_RE.test(aiModel)) throw new BadRequest('Model Name has invalid characters');
  return { aiBaseUrl, aiModel };
}

// The litellm model line is `model: openai/<id>`; api_base is `api_base: <url>`.
// A box rendered by the current installer may still have `api_base:
// os.environ/INFERENCE_BASE_URL` (read from env) — treat that as "not shown".
const MODEL_RE_LINE = /^(\s*)model:\s*openai\/(.+?)\s*$/m;
const BASE_RE_LINE = /^(\s*)api_base:\s*(.+?)\s*$/m;

export function configViewFromYaml(yamlText: string): ConfigView {
  const model = yamlText.match(MODEL_RE_LINE);
  const base = yamlText.match(BASE_RE_LINE);
  const baseVal = base ? base[2] : '';
  return {
    aiModel: model ? model[2] : '',
    aiBaseUrl: baseVal.startsWith('os.environ/') ? '' : baseVal,
  };
}

// Apply the patch to litellm/config.yaml: rewrite the model + api_base lines in
// place, leaving api_key (os.environ) and everything else untouched. Throws if
// the file has no model line to edit (a config we do not recognise).
export function applyConfigToYaml(yamlText: string, patch: ConfigPatch): string {
  if (!MODEL_RE_LINE.test(yamlText)) throw new BadRequest('litellm config has no model line to update');
  let out = yamlText.replace(MODEL_RE_LINE, `$1model: openai/${patch.aiModel}`);
  if (BASE_RE_LINE.test(out)) out = out.replace(BASE_RE_LINE, `$1api_base: ${patch.aiBaseUrl}`);
  return out;
}

// `restart` (not `up -d`): the model + api_base live in the mounted
// litellm/config.yaml, whose CONTENT we just rewrote. `up -d` only re-creates a
// service when its compose CONFIG changes, so it would no-op on a file-content
// change; a restart stops and starts the process, which re-reads the mount.
export function buildReconfigureArgv(): string[] {
  return [...COMPOSE, 'restart', ...RECONFIGURE_SERVICES];
}
