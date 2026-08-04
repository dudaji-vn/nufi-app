#!/usr/bin/env node
/**
 * Validate nufi/adapters.json — the file that keeps agent model traffic on the
 * NuFi gateway.
 *
 * Upstream's built-in defaults egress straight to vendor APIs
 * (packages/plugins/sandbox-providers/kubernetes/src/adapter-defaults.ts).
 * This registry replaces them. A regression here is silent: the app keeps
 * working, agents keep answering, and the guardrails simply stop seeing the
 * traffic. So the invariant is asserted rather than assumed.
 *
 * Checks:
 *   1. Shape matches upstream's `.strict()` zod schema — an unknown key makes
 *      the server throw on boot.
 *   2. Adapter types are ones upstream knows about.
 *   3. Every ENABLED adapter egresses only to the gateway host, and has a
 *      non-empty allow-list. An empty allowFqdns means "no extra egress",
 *      which for an enabled adapter is a broken adapter, not a locked one.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const GATEWAY_HOST = "api.codechi.me";

const ALLOWED_KEYS = new Set([
  "adapterType",
  "enabled",
  "runtimeImage",
  "envKeys",
  "allowFqdns",
  "probeCommand",
  "defaultEnv",
]);

const KNOWN_ADAPTERS = new Set([
  "claude_local",
  "codex_local",
  "gemini_local",
  "cursor_local",
  "opencode_local",
  "pi_local",
]);

const registry = JSON.parse(readFileSync(join(HERE, "adapters.json"), "utf8"));
const problems = [];

if (!Array.isArray(registry)) {
  console.error("adapters.json must be an array of registry entries.");
  process.exit(1);
}

for (const entry of registry) {
  const name = entry.adapterType ?? "<unnamed>";

  for (const key of Object.keys(entry)) {
    if (!ALLOWED_KEYS.has(key)) {
      problems.push(`${name}: unknown key "${key}" — upstream's schema is .strict() and will reject it`);
    }
  }

  if (!KNOWN_ADAPTERS.has(name)) {
    problems.push(`${name}: not an adapter type upstream ships`);
  }

  if (!entry.runtimeImage) {
    problems.push(`${name}: runtimeImage is required`);
  }

  if (!entry.enabled) continue;

  const egress = entry.allowFqdns ?? [];
  if (egress.length === 0) {
    problems.push(`${name}: enabled with an empty allowFqdns — it can reach nothing`);
  }
  for (const fqdn of egress) {
    if (fqdn !== GATEWAY_HOST) {
      problems.push(`${name}: egress to "${fqdn}" bypasses the gateway`);
    }
  }

  const baseUrls = Object.entries(entry.defaultEnv ?? {}).filter(([k]) => k.endsWith("_BASE_URL"));
  if (baseUrls.length === 0) {
    problems.push(`${name}: enabled with no *_BASE_URL in defaultEnv — the harness will use its vendor default`);
  }
  for (const [key, url] of baseUrls) {
    if (!URL.parse(url) || new URL(url).hostname !== GATEWAY_HOST) {
      problems.push(`${name}: ${key}="${url}" does not point at the gateway`);
    }
  }
}

const enabled = registry.filter((e) => e.enabled).length;
console.log(
  `${registry.length} adapters — ${enabled} enabled, ${registry.length - enabled} disabled`,
);

if (problems.length > 0) {
  console.error(`\n${problems.length} problem(s):`);
  for (const p of problems) console.error(`  ${p}`);
  process.exit(1);
}

console.log(`OK — every enabled adapter routes and egresses only to ${GATEWAY_HOST}.`);
