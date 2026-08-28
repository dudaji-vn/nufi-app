import type { Plugin } from "vite";

import { PRODUCT, rebrandAll, rebrandRenderedProps } from "../nufi/rebrand.mjs";

/**
 * NuFi rebrand — a build-time transform, not a source rewrite.
 *
 * apps/agents is vendored from paperclipai/paperclip and must stay
 * byte-identical to the upstream tag so `git subtree pull` keeps working
 * (docs/2026-08-03-nufi-agent-app-design.md §7). The product name, however,
 * appears in ~490 user-visible strings, because Paperclip's i18n is barely
 * adopted (ui/src/i18n/locales/en.json defines three strings; everything else
 * is inline). Renaming those in place would touch hundreds of files and make
 * every upstream copy edit a merge conflict. Renaming them here costs one file.
 *
 * The rules live in ../nufi/rebrand.mjs, shared with
 * nufi/rebrand-server-dist.mjs so the two bundles cannot drift apart.
 *
 * ORDERING MATTERS. This plugin must run AFTER @vitejs/plugin-react, so it is
 * registered after `react()` in vite.config.ts and deliberately carries no
 * `enforce: "pre"`. Most of the product name is JSX text —
 * `<h1>Welcome to Paperclip</h1>` — which is not a string literal in the source
 * at all. Running first missed all of it: 93 occurrences survived into the
 * bundle. After React's transform that text is
 * `_jsx("h1", { children: "Welcome to Paperclip" })`, which the string rule
 * does reach, while the icon stays safe because `<Paperclip />` compiles to
 * `_jsx(Paperclip, {})` — an identifier, never a string.
 */

/**
 * The whole-string rewrite, now that nufi/rebrand-server-dist.mjs applies the
 * same rules to server/dist. Both sides of every comparison say NUFI, so the
 * handoff equality that broke under a one-sided rewrite holds again.
 *
 * If the server transform is ever dropped, this MUST go back to
 * `rebrandRenderedProps` — a one-sided whole-string rewrite is a silent bug,
 * not a cosmetic one.
 */
export const rebrandStrings = rebrandAll;

export { rebrandAll, rebrandRenderedProps };

export function nufiRebrand(): Plugin {
  return {
    name: "nufi-rebrand",

    transform(code, id) {
      // .json is included deliberately. The app-definition files under
      // packages/shared are data, not code, and they carry user-facing
      // guidance text -- "add Paperclip's redirect URI", "share the sheet
      // with the Paperclip robot email". Excluding them shipped the upstream
      // name into the connect screens of three integrations while every
      // brand guard stayed green, because every guard looked at code.
      if (!/\.(json|[jt]sx?)$/.test(id.split("?")[0])) return null;
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
