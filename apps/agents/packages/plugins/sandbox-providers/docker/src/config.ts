/**
 * The environment config as an operator wrote it, checked and defaulted.
 *
 * This is the only file that knows a default value. `container-spec.ts`
 * consumes the parsed shape and never reaches into the raw one.
 */

export class ConfigError extends Error {}

export interface DockerProviderConfig {
  image: string;
  memory: string;
  cpus: number;
  pidsLimit: number;
  egressProxy: string;
  timeoutMs: number;
}

export const DEFAULTS: DockerProviderConfig = Object.freeze({
  image: "ghcr.io/dudaji-vn/nufi-sandbox:main",
  memory: "2g",
  cpus: 2,
  pidsLimit: 512,
  egressProxy: "works-egress:3128",
  timeoutMs: 3_600_000,
});

// A tag after the last slash, or a digest. `ghcr.io/x/y` alone is whatever
// :latest resolves to on the day, which is not a thing to run untrusted code in.
const PINNED_IMAGE = /^[^\s]+(:[\w][\w.-]{0,127}|@sha256:[0-9a-f]{64})$/;
const HOST_PORT = /^[a-zA-Z0-9.-]+:\d{1,5}$/;
const DOCKER_MEMORY = /^\d+(\.\d+)?[bkmg]?$/i;

const UNIT: Record<string, number> = { b: 1, k: 1024, m: 1024 ** 2, g: 1024 ** 3 };

/** "2g" → bytes. Only for a value DOCKER_MEMORY has already accepted. */
export function memoryBytes(size: string): number {
  const m = /^(\d+(?:\.\d+)?)([bkmg]?)$/i.exec(size)!;
  return Math.round(Number(m[1]) * UNIT[(m[2] || "b").toLowerCase()]);
}

// Docker's own floor for --memory. Below it the daemon refuses the create --
// except "0", which it accepts and reads as *no limit*: a sandbox that
// cannot be bounded, reachable through a value the syntax check passes.
export const MIN_MEMORY = "6m";

type Problem = { field: keyof DockerProviderConfig; message: string };

function check(raw: Record<string, unknown>): { config: DockerProviderConfig; problems: Problem[] } {
  const problems: Problem[] = [];
  const out: DockerProviderConfig = { ...DEFAULTS };

  if (raw.image !== undefined) {
    if (typeof raw.image !== "string" || !PINNED_IMAGE.test(raw.image)) {
      problems.push({ field: "image", message: `image must be a pinned reference (tag or digest), got ${JSON.stringify(raw.image)}` });
    } else out.image = raw.image;
  }
  if (raw.memory !== undefined) {
    if (typeof raw.memory !== "string" || !DOCKER_MEMORY.test(raw.memory)) {
      problems.push({ field: "memory", message: `memory must be a Docker size like "2g", got ${JSON.stringify(raw.memory)}` });
    } else if (memoryBytes(raw.memory) < memoryBytes(MIN_MEMORY)) {
      problems.push({ field: "memory", message: `memory must be at least ${MIN_MEMORY} (Docker's minimum), got ${JSON.stringify(raw.memory)}` });
    } else out.memory = raw.memory;
  }
  for (const field of ["cpus", "pidsLimit", "timeoutMs"] as const) {
    const v = raw[field];
    if (v === undefined) continue;
    if (typeof v !== "number" || !Number.isFinite(v) || v <= 0) {
      problems.push({ field, message: `${field} must be a positive number, got ${JSON.stringify(v)}` });
    } else out[field] = v;
  }
  if (raw.egressProxy !== undefined) {
    if (typeof raw.egressProxy !== "string" || !HOST_PORT.test(raw.egressProxy)) {
      problems.push({ field: "egressProxy", message: `egressProxy must be host:port (no scheme), got ${JSON.stringify(raw.egressProxy)}` });
    } else out.egressProxy = raw.egressProxy;
  }
  return { config: out, problems };
}

export function parseConfig(raw: Record<string, unknown>): DockerProviderConfig {
  const { config, problems } = check(raw);
  if (problems.length > 0) {
    throw new ConfigError(problems.map((p) => p.message).join("; "));
  }
  return config;
}

export function validateConfig(
  raw: Record<string, unknown>,
): { ok: boolean; errors: string[]; warnings: string[] } {
  const { problems } = check(raw);
  return { ok: problems.length === 0, errors: problems.map((p) => p.message), warnings: [] };
}
