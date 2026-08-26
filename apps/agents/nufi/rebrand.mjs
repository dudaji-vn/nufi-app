/**
 * The product-name transform, shared by both bundles.
 *
 * It lives here, as plain ESM with no dependencies, because two very different
 * consumers need the identical rules:
 *
 *   - ui/nufi-rebrand.ts   a Vite plugin, running inside the browser build
 *   - nufi/rebrand-server-dist.mjs   a Node script, run over server/dist after tsc
 *
 * They MUST agree. A string renamed on one side and not the other silently
 * breaks every comparison between them — see rebrandAll below.
 */

export const BRAND = "NUFI";
export const PRODUCT = "NUFI Works";

/**
 * Quoted strings are matched WITHOUT newlines. An apostrophe in a comment
 * ("don't") would otherwise open a span that swallows following lines and could
 * rewrite an identifier. Bounding those to one line keeps a mis-parse to the
 * line it started on. Template literals do legitimately span lines.
 */
const STRING_LITERAL = /"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g;

/**
 * Whole word `Paperclip`, never in JSX or identifier position. `Paperclip` is
 * also a lucide-react icon rendered as `<Paperclip />`, and after React's
 * transform as `_jsx(Paperclip, {})` — neither is a string, so neither is
 * reached, but the lookbehind guards the uncompiled form too.
 *
 * The lowercase and compound namespaces are out of reach by construction:
 * `@paperclipai/*`, `paperclip-agent-shim`, `PAPERCLIP_*`, `--paperclip-*`.
 */
const PRODUCT_NAME = /(?<![<\/\w])\bPaperclip\b/g;

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

const RENDERED_PROP_STRING = new RegExp(
  String.raw`(["']?(?:${RENDERED_PROPS.join("|")})["']?\s*:\s*)` +
    String.raw`("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|` +
    "`(?:[^`\\\\]|\\\\.)*`)",
  "g",
);

/**
 * Rewrites only text the client RENDERS. Safe to apply to one side alone,
 * because a rendered prop is not a value anything compares against.
 *
 * Deliberately excluded: `message`, `body`, `detail`, `error`, `name` — measured
 * against the built bundle, that is where server-authored notice bodies live.
 */
export function rebrandRenderedProps(code) {
  return code.replace(
    RENDERED_PROP_STRING,
    (_match, prefix, literal) => prefix + literal.replace(PRODUCT_NAME, BRAND),
  );
}

/**
 * Rewrites EVERY string literal.
 *
 * Only safe when both bundles get it. `ui/src/lib/successful-run-handoff.ts`
 * holds
 *
 *   const SUCCESSFUL_RUN_HANDOFF_REQUIRED_NOTICE_BODY =
 *     "Paperclip needs a disposition before this issue can continue.";
 *   …
 *   return trimmed === SUCCESSFUL_RUN_HANDOFF_REQUIRED_NOTICE_BODY;
 *
 * and the value on the left is a comment body the SERVER wrote. Rename one side
 * and the equality fails silently: the UI stops recognising its own system
 * notices and renders them as ordinary comments. Nothing throws, nothing logs.
 *
 * Those exact notices are not hypothetical — they appeared verbatim during the
 * spike (docs/2026-08-04-nufi-agents-spike-findings.md §3).
 */
export function rebrandAll(code) {
  return code.replace(STRING_LITERAL, (literal) => literal.replace(PRODUCT_NAME, BRAND));
}
