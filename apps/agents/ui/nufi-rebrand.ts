import type { Plugin } from "vite";

/**
 * NuFi rebrand — a build-time transform, not a source rewrite.
 *
 * apps/agents is vendored from paperclipai/paperclip and must stay
 * byte-identical to the upstream tag so `git subtree pull` keeps working
 * (docs/2026-08-03-nufi-agent-app-design.md §7). The product name, however,
 * appears in ~490 user-visible strings — error messages, tooltips, help text —
 * because Paperclip's i18n is barely adopted (ui/src/i18n/locales/en.json
 * defines three strings; everything else is inline).
 *
 * Renaming those in place would touch hundreds of files and make every
 * upstream copy edit a merge conflict. Renaming them here costs one file and
 * leaves the vendored source untouched.
 *
 * WHY STRING LITERALS ONLY
 *
 * `Paperclip` is also a lucide-react icon component, rendered as `<Paperclip />`
 * in at least ten places. A blind word replacement renames the import and
 * breaks the build. So the transform walks string literals and rewrites only
 * inside them.
 *
 * Quoted strings are matched WITHOUT allowing newlines. An apostrophe in a
 * comment ("don't") would otherwise open a span that swallows following lines
 * and could rewrite an identifier. Bounding those matches to one line keeps the
 * blast radius of a mis-parse to the line it started on. Template literals do
 * legitimately span lines, so they are matched across them.
 *
 * As a second guard, a match immediately preceded by `<` or `</` is skipped —
 * that is JSX element position and never a product name.
 *
 * NOT TOUCHED, deliberately:
 *   - `@paperclipai/*` package specifiers, `paperclip-*` binaries and paths
 *   - `PAPERCLIP_*` env vars and `--paperclip-*` CSS custom properties
 *   - LICENSE and every copyright notice — MIT requires they survive verbatim
 * All are lowercase or compound, so the capitalised whole-word pattern below
 * cannot reach them.
 */

const BRAND = "NUFI";
const PRODUCT = "NUFI Agents";

/** Double/single quoted (single line) or backtick (multi-line) literals. */
const STRING_LITERAL = /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g;

/** Whole word `Paperclip`, not in JSX element position. */
const PRODUCT_NAME = /(?<![<\/\w])\bPaperclip\b/g;

export function rebrandStrings(code: string): string {
  return code.replace(STRING_LITERAL, (literal) => literal.replace(PRODUCT_NAME, BRAND));
}

export function nufiRebrand(): Plugin {
  return {
    name: "nufi-rebrand",
    enforce: "pre",

    transform(code, id) {
      if (!/\.[jt]sx?$/.test(id)) return null;
      if (id.includes("/node_modules/")) return null;
      if (!code.includes("Paperclip")) return null;

      const out = rebrandStrings(code);
      return out === code ? null : { code: out, map: null };
    },

    transformIndexHtml(html) {
      return html
        .replace(/<title>[^<]*<\/title>/, `<title>${PRODUCT}</title>`)
        .replace(
          /(<meta\s+name="apple-mobile-web-app-title"\s+content=")[^"]*(")/,
          `$1${PRODUCT}$2`,
        )
        .replace(/(<meta\s+name="theme-color"\s+content=")[^"]*(")/, "$1#080810$2");
    },
  };
}
