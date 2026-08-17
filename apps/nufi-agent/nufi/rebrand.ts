import type { Plugin } from "vite";

/**
 * The product name is rewritten at build time rather than edited into the
 * vendored source.
 *
 * Measured on v1.11.2: 471 occurrences of "Langflow" across 62 frontend
 * files, 308 of them inside the seven locale JSONs under
 * `src/frontend/src/locales/`. Renaming them at the source would make every
 * upstream copy edit a merge conflict — exactly what apps/chat did to
 * itself. This mirrors `apps/agents/ui/nufi-rebrand.ts`, which solved the
 * identical problem for Paperclip.
 *
 * DESIGN — single-pass, no masking.
 *
 * An earlier draft of this transform "protected" excluded regions (import
 * specifiers, URLs, env vars, locale keys) by replacing them with a numbered
 * placeholder (`" ${index} "`) and restoring them afterwards with a regex
 * that looked for bare numbers between spaces. That restore regex cannot
 * tell its own placeholder apart from source text that legitimately
 * contains a bare number between two spaces — "version 5 released", "step 3
 * of 7" — and would silently splice the wrong content back in. See
 * rebrand.test.ts "does not corrupt text that already contains a bare
 * number" for a case that would fail under that design.
 *
 * This version never materialises a placeholder, so there is nothing to
 * collide with. `PATTERN_TS`/`PATTERN_JSON` are each a single regex whose
 * alternatives are tried in order at every position: the excluded-region
 * alternatives (import/export specifiers, URLs, LANGFLOW_* env vars,
 * lower-case langflow.* module paths, and — for JSON only, see below —
 * locale string KEYS) come first, and only the final alternative — the
 * bare product word — is the one `rewrite` ever substitutes. Whichever
 * alternative wins a given match, the whole engine runs in one
 * `String.replace` pass with a single callback that either returns the
 * match verbatim (excluded region) or `PRODUCT` (the product word). No
 * text is ever re-parsed after being written.
 *
 * FIX ROUND 1 — the JSON-key exclusion was firing outside JSON.
 *
 * The original `JSON_KEY` pattern — "a quoted string immediately followed
 * by a colon" — is unambiguous in JSON (that shape can only be a key) but
 * ambiguous in TypeScript, where the identical shape also matches a
 * ternary's true branch (`isBar ? "Langflow" : other`), an object-literal
 * key (`{"Langflow": 1}`), and a type-literal member (`type T = {
 * "Langflow": string }`). All three are ordinary rewritable text, not a
 * namespace to protect, and the miss was silent: no test failure, no build
 * error, no fork-guard signal — a stray "Langflow" would simply ship. See
 * rebrand.test.ts for the reproduction and the fix.
 *
 * `rewrite` now takes a `json` flag and only applies the key exclusion when
 * the caller says the source actually is JSON. `nufiRebrand()` passes it
 * from the module id, which is the one place the file's real type is known
 * for certain.
 */
export const PRODUCT = "NuFi Agent";

/**
 * import/export ... from "..."; a bare `from "..."` re-export clause counts
 * too. Bounded to one line — this codebase's formatter never lets an import
 * statement span lines — so a stray later `;` on the same physical line
 * can't extend the match past the specifier. This is what keeps asset
 * import paths like `@/assets/LangflowLogo.svg` untouched (on top of the
 * word-boundary guard below, which already stops `Langflow` from matching
 * inside the compound `LangflowLogo`).
 */
const IMPORT_FROM = String.raw`(?:import|export)\s[^;\n]*?\bfrom\s+["'][^"'\n]*["']`;

/** A documentation / marketing URL — e.g. https://docs.langflow.org/... */
const URL = String.raw`https?:\/\/[^\s"'<>)]+`;

/** LANGFLOW_* environment variable names (the all-caps namespace). */
const ENV_VAR = String.raw`\bLANGFLOW_[A-Z0-9_]*\b`;

/**
 * Lower-case dotted module namespaces: `langflow.services`,
 * `lfx.langflow_core`. Redundant with the case-sensitive product-word match
 * below (these are always lower-case by convention) but named explicitly so
 * the rule documents the invariant instead of relying on an accident of
 * case.
 */
const MODULE_PATH = String.raw`\blangflow(?:[._][A-Za-z0-9_]+)+`;

/**
 * A quoted string immediately followed by a colon. In JSON that shape can
 * only be an object KEY — the seven locale files are flat `"dotted.key":
 * "Value"` maps, 308 of the 471 brand hits live in the values, and every
 * key must survive untouched or i18next's lookup misses and the UI renders
 * the raw key path instead of translated text. Checked against all seven
 * locale files: no key contains the capitalised word "Langflow" today, but
 * the rule is structural, not data-dependent, so a key upstream adds later
 * can't silently start breaking translations.
 *
 * ONLY safe in JSON. In TypeScript the same shape also matches a ternary
 * true-branch, an object-literal key, and a type-literal member — none of
 * which need the product name preserved (see the FIX ROUND 1 note above).
 * `rewrite` therefore only includes this alternative when told the source
 * is JSON; do not fold it into the always-on skip list.
 */
const JSON_KEY = String.raw`"(?:[^"\\]|\\.)*"(?=\s*:)`;

/**
 * The product word itself: capitalised, whole-word only. `\b` on both sides
 * means it never matches inside an ALL-CAPS env namespace (`LANGFLOW_*`,
 * different case), a lower-case module path (`langflow.services`, different
 * case), or a compound identifier glued onto it (`LangflowLogo`,
 * `LangflowButtonRedirectTarget`, `CustomLangflowCounts` — no boundary
 * between "Langflow" and the following word character).
 */
const PRODUCT_NAME = String.raw`\bLangflow\b`;

const SKIP_ALWAYS = `(?:${IMPORT_FROM})|(?:${URL})|(?:${ENV_VAR})|(?:${MODULE_PATH})`;

/** Non-JSON sources: no key exclusion, so ternaries/type-literals rewrite normally. */
const PATTERN_TS = new RegExp(`${SKIP_ALWAYS}|(?<target>${PRODUCT_NAME})`, "g");

/** JSON sources only: adds the key exclusion, since a colon there can only mean a key. */
const PATTERN_JSON = new RegExp(`${SKIP_ALWAYS}|(?:${JSON_KEY})|(?<target>${PRODUCT_NAME})`, "g");

/**
 * @param json Whether `code` is JSON (a locale file). Defaults to `false`.
 *   The default errs toward REWRITING a colon-following quoted string
 *   rather than preserving it: in the overwhelmingly common case (55 of the
 *   62 baseline files are not JSON) that shape is ordinary code — a ternary
 *   branch, an object key, a type-literal member — and preserving it by
 *   mistake is the exact silent, untested, unguarded miss this flag exists
 *   to close. Getting the default wrong for an actual locale file instead
 *   produces a loud failure (a broken i18next lookup, easy to spot), which
 *   is the failure mode we'd rather have. `nufiRebrand()` never relies on
 *   this default — it always passes `json` explicitly from the real module
 *   id — so the default only matters for direct callers (tests, future
 *   scripts) that omit it.
 */
export function rewrite(code: string, json = false): string {
  const pattern = json ? PATTERN_JSON : PATTERN_TS;
  return code.replace(pattern, (match, ...rest) => {
    const groups = rest[rest.length - 1] as { target?: string } | undefined;
    return groups?.target ? PRODUCT : match;
  });
}

export function nufiRebrand(): Plugin {
  return {
    name: "nufi-rebrand",
    enforce: "pre",
    transform(code, id) {
      const path = id.split("?")[0];
      // NOTE: the .html branch below only ever fires during a production
      // build. Vite serves index.html through its own `transformIndexHtml`
      // hook, not the generic module `transform` hook used here, so this
      // never runs against index.html in `vite dev`. Kept for build-time
      // coverage (and in case a future .html file enters the module graph
      // via an import), but don't assume it covers index.html in dev.
      if (!/\.(?:tsx?|jsx?|json|html)$/.test(path)) return null;
      if (id.includes("/node_modules/")) return null;
      const out = rewrite(code, path.endsWith(".json"));
      return out === code ? null : { code: out, map: null };
    },
  };
}
