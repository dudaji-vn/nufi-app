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
 * collide with. `PATTERN` is a single regex whose alternatives are tried in
 * order at every position: the excluded-region alternatives (import/export
 * specifiers, URLs, LANGFLOW_* env vars, lower-case langflow.* module
 * paths, and locale/object-literal string KEYS) come first, and only the
 * final alternative — the bare product word — is the one `rewrite` ever
 * substitutes. Whichever alternative wins a given match, the whole engine
 * runs in one `String.replace` pass with a single callback that either
 * returns the match verbatim (excluded region) or `PRODUCT` (the product
 * word). No text is ever re-parsed after being written.
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
 * A quoted string immediately followed by a colon — a JSON/object-literal
 * KEY, not a value. The seven locale files are flat `"dotted.key": "Value"`
 * maps; 308 of the 471 brand hits live in the values, and every key must
 * survive untouched or i18next's lookup misses and the UI renders the raw
 * key path instead of translated text. Checked against all seven locale
 * files: no key contains the capitalised word "Langflow" today, but the
 * rule is structural, not data-dependent, so a key upstream adds later
 * can't silently start breaking translations.
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

const PATTERN = new RegExp(
  `(?:${IMPORT_FROM})|(?:${URL})|(?:${ENV_VAR})|(?:${MODULE_PATH})|(?:${JSON_KEY})|(?<target>${PRODUCT_NAME})`,
  "g",
);

export function rewrite(code: string): string {
  return code.replace(PATTERN, (match, ...rest) => {
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
      if (!/\.(?:tsx?|jsx?|json|html)$/.test(path)) return null;
      if (id.includes("/node_modules/")) return null;
      const out = rewrite(code);
      return out === code ? null : { code: out, map: null };
    },
  };
}
