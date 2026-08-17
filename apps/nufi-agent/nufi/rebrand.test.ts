import { describe, expect, it } from "bun:test";

import { rewrite } from "./rebrand";

/**
 * Run with `bun test` from `apps/nufi-agent/nufi/`, not `vitest`. This
 * package (like apps/agents/nufi/adapter) is standalone: it must build and
 * test outside the vendored Langflow frontend, which is a jest workspace
 * (`apps/nufi-agent/src/frontend/package.json` → `"test": "jest"`), not a
 * vitest one. Adding vitest to that package.json would itself be an
 * upstream-file edit needing a new fork-guard allowlist entry, for a
 * test-runner preference no other part of this fork needs.
 */
describe("rewrite", () => {
  it("renames the product in user-facing copy", () => {
    expect(rewrite('const t = "Welcome to Langflow";')).toBe(
      'const t = "Welcome to NuFi Agent";',
    );
  });

  it("rewrites the same word inside a locale JSON value (json: true)", () => {
    expect(rewrite('{"welcome": "Langflow guide"}', true)).toBe('{"welcome": "NuFi Agent guide"}');
  });

  /**
   * 308 of the 471 brand hits are locale VALUES. Keys are addressed by code
   * and must survive, or every lookup misses and the UI renders raw key
   * paths. The key exclusion only applies when `json` is true — see FIX
   * ROUND 1 below for why it must not apply unconditionally.
   */
  it("never rewrites a locale key (json: true)", () => {
    expect(rewrite('{"langflow_version": "1.11.2"}', true)).toBe('{"langflow_version": "1.11.2"}');
  });

  /**
   * The lower-case key above never contains the capitalised word "Langflow"
   * (case sensitivity alone would protect it). This case proves the key
   * exclusion is structural — a colon-following quoted string — not an
   * accident of case: the key here DOES contain the exact word, and only
   * the value gets rewritten.
   */
  it("never rewrites a locale key even when it contains the exact product word (json: true)", () => {
    expect(rewrite('{"Langflow": "Langflow guide"}', true)).toBe('{"Langflow": "NuFi Agent guide"}');
  });

  /**
   * FIX ROUND 1 — review finding: "JSON_KEY cannot distinguish a locale key
   * from a ternary branch, and the miss is silent."
   *
   * The pre-fix implementation applied the colon-following-quoted-string
   * exclusion unconditionally, so it also matched a ternary true-branch, an
   * object-literal key, and a TS type-literal member — none of which are
   * JSON, none of which need the product name preserved. The miss produced
   * no test failure, no build error, and no fork-guard signal: a stray
   * "Langflow" would simply ship in a shape that resembles source used
   * nowhere in the v1.11.2 baseline today but is a common enough React/TS
   * idiom to show up in a future upstream sync. These three all reproduce
   * the review's examples and default `json` to false (the caller passes
   * nothing — this is the codepath every non-JSON file in the app takes).
   */
  describe("FIX ROUND 1 — the JSON-key exclusion must not fire outside JSON", () => {
    it("rewrites a ternary true-branch in a non-JSON (.tsx-shaped) context", () => {
      expect(rewrite('const label = isBar ? "Langflow" : other;')).toBe(
        'const label = isBar ? "NuFi Agent" : other;',
      );
    });

    it("rewrites a TS type-literal member in a non-JSON (.tsx-shaped) context", () => {
      expect(rewrite('type T = { "Langflow": string };')).toBe('type T = { "NuFi Agent": string };');
    });

    it("rewrites an object-literal key in a non-JSON (.tsx-shaped) context", () => {
      expect(rewrite('const x = {"Langflow": 1};')).toBe('const x = {"NuFi Agent": 1};');
    });

    it("still leaves the same shape untouched when json: true is passed explicitly", () => {
      expect(rewrite('{"Langflow": "1.11.2"}', true)).toBe('{"Langflow": "1.11.2"}');
    });
  });

  /**
   * Asset filenames stay upstream on purpose (Task 1 Step 4). Rewriting an
   * import path breaks the build.
   */
  it("leaves import paths and asset filenames alone", () => {
    const src = 'import Logo from "@/assets/LangflowLogo.svg";';
    expect(rewrite(src)).toBe(src);
  });

  it("leaves python package and module namespaces alone", () => {
    expect(rewrite("from langflow.services import x")).toBe("from langflow.services import x");
    expect(rewrite('"lfx.langflow_core"')).toBe('"lfx.langflow_core"');
  });

  it("leaves env var namespaces alone", () => {
    expect(rewrite("LANGFLOW_AUTO_LOGIN=true")).toBe("LANGFLOW_AUTO_LOGIN=true");
  });

  it("leaves documentation urls alone", () => {
    const src = '"https://docs.langflow.org/get-started"';
    expect(rewrite(src)).toBe(src);
  });

  /**
   * The bug in an earlier draft: it masked excluded regions with a numbered
   * placeholder (` ${index} `) and restored them with a regex matching any
   * bare number between spaces. Source text that already contains a bare
   * number between two spaces — like this one — collides with that restore
   * regex and gets silently corrupted. This implementation never
   * materialises a placeholder, so there is nothing to collide with; this
   * test would fail under the masking design.
   */
  it("does not corrupt text that already contains a bare number", () => {
    const src = 'const t = "Langflow step 3 of 7";';
    expect(rewrite(src)).toBe('const t = "NuFi Agent step 3 of 7";');
  });

  it("does not touch a compound identifier glued onto the product word", () => {
    const src = 'import CustomLangflowCounts from "@/customization/components/custom-langflow-counts";';
    expect(rewrite(src)).toBe(src);
    expect(rewrite("export const LangflowButtonRedirectTarget = () => {};")).toBe(
      "export const LangflowButtonRedirectTarget = () => {};",
    );
  });

  it("is a no-op when the product word never appears", () => {
    const src = 'const x = "hello world";';
    expect(rewrite(src)).toBe(src);
  });
});
