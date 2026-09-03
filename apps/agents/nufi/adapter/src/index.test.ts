import { describe, expect, it } from "bun:test";

import { models } from "./index";

describe("the models this adapter offers", () => {
  /**
   * `gemini` works on the gateway and cannot work here.
   *
   * The gateway's G1 control classifies a tool result as `untrusted` —
   * threshold 0.50, one detector, no corroboration required — and the injection
   * classifier scores benign text near 1.0. Measured on the smallest tool
   * result that can exist, `{"ok":true}`: refused as `role: tool`, fine as
   * `role: user`. So every agent turn after the first is refused.
   *
   * `nufi-agent` resolves to the same backend and is the one model name G1
   * exempts. Offering the other one is not a cosmetic mistake: three agents
   * were hired against `gemini` during a gate test and all four of their tasks
   * died on the second turn.
   */
  it("offers only the alias the gateway exempts", () => {
    expect(models.map((m) => m.id)).toEqual(["nufi-agent"]);
  });

  it("does not offer a model that cannot finish a run", () => {
    expect(models.map((m) => m.id)).not.toContain("gemini");
  });

  it("labels it so a person picking from a dropdown knows what they get", () => {
    expect(models[0].label).toMatch(/gemini/i);
  });
});
