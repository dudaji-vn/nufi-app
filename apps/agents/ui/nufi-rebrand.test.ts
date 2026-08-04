import { describe, expect, it } from "vitest";

import { rebrandStrings } from "./nufi-rebrand";

/**
 * The transform rewrites the product name inside string literals only. The
 * cases that matter are the ones it must NOT touch: `Paperclip` is also a
 * lucide-react icon, and the package/binary/env/CSS namespaces are load-bearing.
 */
describe("rebrandStrings", () => {
  it("leaves the lucide Paperclip icon import alone", () => {
    const src = 'import { Paperclip } from "lucide-react";';
    expect(rebrandStrings(src)).toBe(src);
  });

  it("leaves the icon in JSX element position alone", () => {
    const src = '<Paperclip className="h-4 w-4" />';
    expect(rebrandStrings(src)).toBe(src);
  });

  it("leaves the icon alone inside a ternary", () => {
    const src = "{copied ? <Check /> : <Paperclip className=\"h-3\" />}";
    expect(rebrandStrings(src)).toBe(src);
  });

  it("does not let an apostrophe in a comment reach a later identifier", () => {
    const src = "// don't rename this <Paperclip /> icon usage";
    expect(rebrandStrings(src)).toBe(src);
  });

  it("renames the product in a double-quoted string", () => {
    expect(rebrandStrings('"Paperclip needs a disposition."')).toBe('"NUFI needs a disposition."');
  });

  it("renames the product in a template literal", () => {
    expect(rebrandStrings("`Paperclip retried this task.`")).toBe("`NUFI retried this task.`");
  });

  it("renames a hyphenated compound built on the product name", () => {
    expect(rebrandStrings('"the stable Paperclip-managed bundle"')).toBe(
      '"the stable NUFI-managed bundle"',
    );
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
