import { describe, expect, it } from "vitest";

import { rebrandStrings } from "./nufi-rebrand";

/**
 * The transform rewrites the product name in rendered props only. Two families
 * of case matter, and the second is the one that cost a debugging session:
 *
 *   1. `Paperclip` is a lucide-react icon, and the package/binary/env/CSS
 *      namespaces are load-bearing — none may be touched.
 *   2. Some `Paperclip` strings are protocol values compared against text the
 *      server wrote. The server is not transformed, so renaming those breaks an
 *      equality check silently.
 */
describe("rebrandStrings", () => {
  describe("renders", () => {
    it("renames JSX text, once React has compiled it to a children prop", () => {
      expect(rebrandStrings('_jsx("h1", { children: "Welcome to Paperclip" })')).toBe(
        '_jsx("h1", { children: "Welcome to NUFI" })',
      );
    });

    it("renames a placeholder", () => {
      expect(rebrandStrings('_jsx("input", { placeholder: "Search Paperclip" })')).toBe(
        '_jsx("input", { placeholder: "Search NUFI" })',
      );
    });

    it("renames a quoted prop key", () => {
      expect(rebrandStrings('{ "aria-label": "Open Paperclip menu" }')).toBe(
        '{ "aria-label": "Open NUFI menu" }',
      );
    });

    it("renames inside a template literal prop", () => {
      expect(rebrandStrings("{ title: `Paperclip retried this task.` }")).toBe(
        "{ title: `NUFI retried this task.` }",
      );
    });

    it("renames a hyphenated compound", () => {
      expect(rebrandStrings('{ description: "the Paperclip-managed bundle" }')).toBe(
        '{ description: "the NUFI-managed bundle" }',
      );
    });
  });

  /**
   * These were unsafe while only the client was renamed: the constants below
   * are compared against comment bodies the SERVER wrote, and renaming one side
   * makes the equality fail silently. They are safe now because
   * nufi/rebrand-server-dist.mjs applies the identical rules to server/dist, so
   * both sides say NUFI.
   *
   * If that server step is ever dropped, these tests should be reverted along
   * with it — they encode a precondition, not a preference.
   */
  describe("rewrites protocol values too, because the server matches", () => {
    it("renames a bare string constant", () => {
      expect(
        rebrandStrings(
          'const NOTICE_BODY = "Paperclip needs a disposition before this issue can continue.";',
        ),
      ).toBe('const NOTICE_BODY = "NUFI needs a disposition before this issue can continue.";');
    });

    it("renames a bare call argument", () => {
      expect(rebrandStrings('toast("Paperclip failed to dispatch")')).toBe(
        'toast("NUFI failed to dispatch")',
      );
    });

    /**
     * Regex literals are still not string literals, so this one is untouched by
     * design. It matches a server-written body, and the server transform
     * renames that body — so the pattern must be updated by hand if it ever
     * stops matching. Recorded here rather than silently tolerated.
     */
    it("still leaves a regex literal alone, which the server rename must account for", () => {
      const src = "/^Paperclip exhausted the bounded successful-run handoff\\b/i.test(trimmed)";
      expect(rebrandStrings(src)).toBe(src);
    });
  });

  describe("leaves identifiers and namespaces alone", () => {
    it("leaves the lucide Paperclip icon import", () => {
      const src = 'import { Paperclip } from "lucide-react";';
      expect(rebrandStrings(src)).toBe(src);
    });

    it("leaves the icon in compiled JSX call position", () => {
      const src = '_jsx(Paperclip, { className: "h-4 w-4" })';
      expect(rebrandStrings(src)).toBe(src);
    });

    it("leaves the icon in uncompiled JSX element position", () => {
      const src = '<Paperclip className="h-4 w-4" />';
      expect(rebrandStrings(src)).toBe(src);
    });

    it.each([
      ['import x from "@paperclipai/adapter-utils";', "package specifier"],
      ['const p = "paperclip-agent-shim";', "binary name"],
      ["css`--paperclip-doc-annotation-highlight-open: #fef`", "CSS custom property"],
      ["env.PAPERCLIP_API_URL", "environment variable"],
    ])("leaves %s untouched (%s)", (src) => {
      expect(rebrandStrings(src)).toBe(src);
    });
  });
});
