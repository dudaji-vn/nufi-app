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

  describe("leaves protocol values alone", () => {
    it("does not rename a bare string constant", () => {
      const src =
        'const NOTICE_BODY = "Paperclip needs a disposition before this issue can continue.";';
      expect(rebrandStrings(src)).toBe(src);
    });

    it("does not rename inside a regex literal", () => {
      const src = "/^Paperclip exhausted the bounded successful-run handoff\\b/i.test(trimmed)";
      expect(rebrandStrings(src)).toBe(src);
    });

    it("does not rename a bare call argument", () => {
      const src = 'toast("Paperclip failed to dispatch")';
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
