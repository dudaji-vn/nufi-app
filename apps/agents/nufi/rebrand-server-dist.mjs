#!/usr/bin/env node
/**
 * Apply the product-name transform to the server bundle after `tsc`.
 *
 * The UI gets its rename from a Vite plugin. The server builds with plain tsc
 * (server/package.json "build"), so there is no plugin hook — this rewrites the
 * emitted JS in place.
 *
 * It must run on EVERY server build. If it does not, the two bundles disagree
 * and every string compared between them silently stops matching: the client
 * looks for "NUFI needs a disposition…" while the server keeps writing
 * "Paperclip needs a disposition…". Nothing throws.
 *
 * Usage:
 *   node apps/agents/nufi/rebrand-server-dist.mjs [dist-dir]
 *   node apps/agents/nufi/rebrand-server-dist.mjs --check [dist-dir]
 *
 * `--check` rewrites nothing and exits non-zero if any file still needs it —
 * for CI, and for catching a Dockerfile that forgot the step.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { rebrandAll } from "./rebrand.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));

const args = process.argv.slice(2);
const check = args.includes("--check");
const dist = args.find((a) => !a.startsWith("--")) ?? join(HERE, "..", "server", "dist");

/**
 * `.d.ts` as well as `.js`. Declarations are not executed, so leaving them
 * alone is harmless at runtime — but tsc emits literal types for exported
 * string constants:
 *
 *   export declare const SUCCESSFUL_RUN_HANDOFF_REQUIRED_NOTICE_BODY =
 *     "Paperclip needs a disposition before this issue can continue.";
 *
 * while the matching .js now says NUFI. A consumer comparing against that
 * constant would typecheck against a literal the runtime never produces. A
 * declaration that disagrees with its own implementation is worse than no
 * declaration.
 */
async function* emittedFiles(dir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch (err) {
    throw new Error(`cannot read ${dir}: ${err.message} — has the server been built?`);
  }
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* emittedFiles(path);
    else if (entry.name.endsWith(".js") || entry.name.endsWith(".d.ts")) yield path;
  }
}

let scanned = 0;
let changed = 0;
const pending = [];

for await (const path of emittedFiles(dist)) {
  scanned++;
  const before = readFileSync(path, "utf8");
  if (!before.includes("Paperclip")) continue;

  const after = rebrandAll(before);
  if (after === before) continue;

  if (check) {
    pending.push(path);
  } else {
    writeFileSync(path, after);
  }
  changed++;
}

if (check) {
  console.log(`checked ${scanned} file(s) in ${dist}`);
  if (pending.length > 0) {
    console.error(`\n${pending.length} file(s) still carry the upstream product name:`);
    for (const p of pending.slice(0, 10)) console.error(`  ${p}`);
    if (pending.length > 10) console.error(`  … and ${pending.length - 10} more`);
    console.error(
      "\nThe server build did not run this script. Client and server will disagree,\n" +
        "and every string compared between them stops matching without an error.",
    );
    process.exit(1);
  }
  console.log("OK — the server bundle carries the NuFi product name.");
} else {
  console.log(`rebranded ${changed} of ${scanned} server file(s) in ${dist}`);
}
