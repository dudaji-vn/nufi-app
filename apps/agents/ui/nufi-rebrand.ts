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

/**
 * WHY THIS IS AN ALLOW-LIST AND NOT "EVERY STRING".
 *
 * An earlier version rewrote the product name inside every string literal. That
 * is unsafe, and measurably so. `ui/src/lib/successful-run-handoff.ts` holds
 *
 *   const SUCCESSFUL_RUN_HANDOFF_REQUIRED_NOTICE_BODY =
 *     "Paperclip needs a disposition before this issue can continue.";
 *   …
 *   return trimmed === SUCCESSFUL_RUN_HANDOFF_REQUIRED_NOTICE_BODY;
 *
 * The value on the left comes from a comment body the SERVER wrote, and the
 * server is not transformed — this is a Vite plugin, so it only ever reaches the
 * browser bundle. Renaming the constant therefore breaks the comparison
 * silently: the UI stops recognising its own system notices and renders them as
 * ordinary comments. Nothing throws.
 *
 * So the rule is: rewrite what the client RENDERS, never what it COMPARES.
 * After React's transform, rendered text is a prop on a `_jsx(...)` call, which
 * is what the property allow-list below targets. A bare string constant is left
 * alone, because a constant is exactly the shape a protocol value takes.
 *
 * The cost of this is coverage: a string passed as a bare argument
 * (`toast("Paperclip failed")`) is not rewritten. That is the intended trade —
 * a missed rename is cosmetic, a broken equality is a bug you find in
 * production.
 */
const RENDERED_PROPS = [
  "children",
  "title",
  "placeholder",
  "alt",
  "label",
  "description",
  "summary",
  "tooltip",
  "helpText",
  "helperText",
  "guidanceMd",
  "hint",
  "heading",
  "subtitle",
  "caption",
  "aria-label",
  "ariaLabel",
];

/**
 * Deliberately NOT on the list: `message`, `body`, `detail`, `error`, `name`.
 * Measured against the built bundle, those are where the server-authored notice
 * bodies live — the same family as the handoff constant above. They are the
 * strings most likely to be compared, and least safe to rewrite from one side.
 */

const RENDERED_PROP_STRING = new RegExp(
  String.raw`(["']?(?:${RENDERED_PROPS.join("|")})["']?\s*:\s*)` +
    String.raw`("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|` + "`(?:[^`\\\\]|\\\\.)*`)",
  "g",
);

/** Whole word `Paperclip`, never in JSX or identifier position. */
const PRODUCT_NAME = /(?<![<\/\w])\bPaperclip\b/g;

export function rebrandStrings(code: string): string {
  return code.replace(
    RENDERED_PROP_STRING,
    (_match, prefix: string, literal: string) => prefix + literal.replace(PRODUCT_NAME, BRAND),
  );
}

/**
 * ORDERING MATTERS. This plugin must run AFTER @vitejs/plugin-react, so it is
 * registered after `react()` in vite.config.ts and deliberately carries no
 * `enforce: "pre"`.
 *
 * Most of the product name is JSX text — `<h1>Welcome to Paperclip</h1>` — which
 * is not a string literal in the source at all. Running first missed all of it
 * (93 occurrences survived into the bundle). Running after React's transform,
 * that text has become `_jsx("h1", { children: "Welcome to Paperclip" })`, which
 * the string-literal rule does reach.
 *
 * The icon stays safe for the same reason: `<Paperclip />` compiles to
 * `_jsx(Paperclip, {})`, an identifier, never a string.
 */
export function nufiRebrand(): Plugin {
  return {
    name: "nufi-rebrand",

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
