import { describe, expect, it } from "vitest";
import {
  SUCCESSFUL_RUN_HANDOFF_ESCALATED_ACTION,
  SUCCESSFUL_RUN_HANDOFF_EXHAUSTED_NOTICE_BODY,
  SUCCESSFUL_RUN_HANDOFF_REQUIRED_ACTION,
  SUCCESSFUL_RUN_HANDOFF_REQUIRED_NOTICE_BODY,
  SUCCESSFUL_RUN_HANDOFF_RESOLVED_ACTION,
  isSuccessfulRunHandoffComment,
  isSuccessfulRunHandoffEscalationComment,
  successfulRunHandoffActivityTone,
} from "./successful-run-handoff";

describe("successful run handoff UI helpers", () => {
  it("matches both required and escalated production comments", () => {
    expect(isSuccessfulRunHandoffComment(SUCCESSFUL_RUN_HANDOFF_REQUIRED_NOTICE_BODY)).toBe(true);
    expect(isSuccessfulRunHandoffComment("## This issue still needs a next step\n\n- Source run: abc")).toBe(true);
    expect(isSuccessfulRunHandoffComment("## Successful run missing issue disposition\n\n- Source run: abc")).toBe(true);
    expect(isSuccessfulRunHandoffComment(SUCCESSFUL_RUN_HANDOFF_EXHAUSTED_NOTICE_BODY)).toBe(true);
    expect(
      isSuccessfulRunHandoffComment(
        "Paperclip exhausted the bounded successful-run handoff correction for this issue, but it still has no clear next-step disposition.",
      ),
    ).toBe(true);
    expect(
      isSuccessfulRunHandoffEscalationComment(
        "Paperclip exhausted the bounded successful-run handoff correction for this issue, but it still has no clear next-step disposition.",
      ),
    ).toBe(true);
    expect(isSuccessfulRunHandoffComment("Ordinary issue comment")).toBe(false);
  });

  it("returns shared tones for required, escalated, and neutral activity", () => {
    expect(successfulRunHandoffActivityTone(SUCCESSFUL_RUN_HANDOFF_REQUIRED_ACTION).className).toContain("amber");
    expect(successfulRunHandoffActivityTone(SUCCESSFUL_RUN_HANDOFF_ESCALATED_ACTION).className).toContain("red");
    expect(successfulRunHandoffActivityTone(SUCCESSFUL_RUN_HANDOFF_RESOLVED_ACTION).className).toContain("border");
  });

  // The server, after the rebrand, emits "NUFI exhausted the bounded
  // corrective handoff ...". The old pattern was anchored on the upstream
  // product name AND on different wording, so it matched neither. This is the
  // string that actually arrives.
  it("matches the escalation wording the server really emits", () => {
    expect(
      isSuccessfulRunHandoffEscalationComment(
        "NUFI exhausted the bounded corrective handoff for this issue, but it still has no clear next-step disposition.",
      ),
    ).toBe(true);
  });

  it("does not depend on the product name", () => {
    expect(
      isSuccessfulRunHandoffEscalationComment(
        "Anything exhausted the bounded corrective handoff for this issue.",
      ),
    ).toBe(true);
  });
});
