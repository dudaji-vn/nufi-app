import { describe, expect, it } from "bun:test";

import { resolveModelKey } from "./client";

describe("resolveModelKey", () => {
  /**
   * The point of the whole connect flow: a per-user secret bound to the agent's
   * env reaches the run through `ctx.config.env`, so each member calls the
   * gateway as themselves. Without this the adapter would read the shared
   * process-wide key and the attribution would be a lie.
   */
  it("prefers the value resolved into config env", () => {
    const key = resolveModelKey(
      { env: { NUFI_MODEL_API_KEY: "sk-mine" } },
      "NUFI_MODEL_API_KEY",
      { NUFI_MODEL_API_KEY: "sk-shared" },
    );
    expect(key).toBe("sk-mine");
  });

  it("falls back to process env when no secret is bound", () => {
    const key = resolveModelKey({}, "NUFI_MODEL_API_KEY", { NUFI_MODEL_API_KEY: "sk-shared" });
    expect(key).toBe("sk-shared");
  });

  it("honours a custom env var name on both paths", () => {
    expect(resolveModelKey({ env: { OTHER: "sk-a" } }, "OTHER", {})).toBe("sk-a");
    expect(resolveModelKey({}, "OTHER", { OTHER: "sk-b" })).toBe("sk-b");
  });

  /**
   * An unset binding must not shadow a working process env. Paperclip writes
   * `env: {}` whenever the agent has an env block at all, so an empty string
   * here is the normal shape of "not configured", not a deliberate override.
   */
  it("ignores an empty or blank bound value and falls through", () => {
    expect(resolveModelKey({ env: { K: "" } }, "K", { K: "sk-shared" })).toBe("sk-shared");
    expect(resolveModelKey({ env: { K: "   " } }, "K", { K: "sk-shared" })).toBe("sk-shared");
  });

  it("returns empty when neither source has it", () => {
    expect(resolveModelKey({ env: {} }, "K", {})).toBe("");
  });

  /**
   * `config.env` arrives from the wire as unknown. A non-object, or a non-string
   * value under the key, must not throw inside a run — it must read as absent.
   */
  it("survives a malformed env block", () => {
    expect(resolveModelKey({ env: "nope" as unknown }, "K", { K: "sk-shared" })).toBe("sk-shared");
    expect(resolveModelKey({ env: { K: 42 as unknown } }, "K", { K: "sk-shared" })).toBe("sk-shared");
    expect(resolveModelKey({ env: null as unknown }, "K", {})).toBe("");
  });

  it("trims surrounding whitespace from a bound value", () => {
    expect(resolveModelKey({ env: { K: " sk-mine\n" } }, "K", {})).toBe("sk-mine");
  });
});
