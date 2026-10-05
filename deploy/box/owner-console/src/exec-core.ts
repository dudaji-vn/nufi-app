// Pure exec allowlist: no fs, no spawn. Single source of truth shared by the
// console (src/exec.ts) and the owner-exec sidecar.
export const SERVICES = ['librechat', 'litellm-proxy', 'rag_api', 'ollama', 'caddy', 'mongodb', 'postgres', 'studio'] as const;
export const READ_CMDS = ['status', 'logs', 'logs librechat', 'doctor', 'support'] as const;
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

export function buildReadArgv(cmd: string): string[] | null {
  if (!isIn(READ_CMDS, cmd)) throw new BadRequest('invalid command');
  switch (cmd) {
    case 'status':
      return [...COMPOSE, 'ps'];
    case 'logs':
      return [...COMPOSE, 'logs', '--no-color', '--tail=200'];
    case 'logs librechat':
      return [...COMPOSE, 'logs', '--no-color', '--tail=200', 'librechat'];
    default:
      return null; // doctor / support: informational only, never executed
  }
}
