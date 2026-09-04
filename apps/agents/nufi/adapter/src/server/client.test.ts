import { describe, expect, it } from "bun:test";

import {
  DEFAULT_AGENT_MODEL,
  buildModel,
  requireRunToken,
  resolveModelKey,
  resolveModelName,
  shouldRetryGateway,
} from "./client";

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

describe("requireRunToken", () => {
  /**
   * The whole point of the guard: an empty token is not "anonymous access", it
   * is a 404 on every issue in the company, which reads as data loss rather
   * than a credential problem.
   */
  it("refuses an absent token and names the cause", () => {
    expect(() => requireRunToken("")).toThrow(/supportsLocalAgentJwt/);
    expect(() => requireRunToken("   ")).toThrow(/No Paperclip run token/);
  });

  it("passes a real token through untouched", () => {
    expect(requireRunToken("eyJhbGciOi.J9.sig")).toBe("eyJhbGciOi.J9.sig");
  });
});

describe("shouldRetryGateway", () => {
  /**
   * "A security check could not run, so this request was refused rather than
   * sent unchecked. This is usually temporary — please retry." Taking the
   * gateway at its word, and only there.
   */
  it("retries a guardrail that could not run", () => {
    expect(shouldRetryGateway(503, '{"param":"GUARDRAIL_UNAVAILABLE"}')).toBe(true);
  });

  /**
   * A refusal that names a policy is a decision, not a hiccup. Retrying it
   * would be arguing with the security stack until it gives in.
   */
  it("never retries a policy decision", () => {
    expect(shouldRetryGateway(400, '{"param":"LLM01_INJECTION"}')).toBe(false);
    expect(shouldRetryGateway(403, '{"param":"nufi_guardrail_blocked"}')).toBe(false);
  });

  it("leaves ordinary failures alone", () => {
    expect(shouldRetryGateway(401, "bad key")).toBe(false);
    expect(shouldRetryGateway(429, "rate limited")).toBe(false);
    expect(shouldRetryGateway(503, "upstream gone")).toBe(false);
  });
});

describe("the model an agent calls", () => {
  /**
   * The default is a security boundary, not a preference.
   *
   * `nufi-agent` is the single model name G1 exempts, and the exemption exists
   * because a tool-calling agent cannot pass that control at all: a tool result
   * is classified `untrusted`, which blocks on one detector at threshold 0.50,
   * and the classifier scores benign text near 1.0. Measured on the smallest
   * possible tool result — `{"ok":true}` — blocked as role=tool, fine as
   * role=user.
   *
   * Defaulting to `gemini` would kill every run on its second turn. Exempting
   * `gemini` instead would strip prompt-injection defence from every chat user
   * to save one loop. The label is what keeps the hole the size of the problem.
   */
  it("defaults to the alias the exemption is scoped to", () => {
    const model = buildModel({
      runId: "r",
      agent: { id: "a", companyId: "c" },
      config: {},
      context: {},
      onLog: async () => {},
    });
    expect(model).toBeDefined();
    // The default lives in client.ts; assert on the contract the policy relies on.
    expect(DEFAULT_AGENT_MODEL).toBe("nufi-agent");
  });

  it("still lets an operator name a different model", () => {
    expect(resolveModelName({ model: "Nufi-lab/models/gemini-2.5-pro" })).toBe(
      "Nufi-lab/models/gemini-2.5-pro",
    );
    expect(resolveModelName({})).toBe(DEFAULT_AGENT_MODEL);
  });
});
