import { describe, expect, it } from "bun:test";

import { buildPrompt, resolveDisposition } from "./disposition";

/**
 * The spike (docs/2026-08-04-nufi-agents-spike-findings.md §3) showed what
 * happens when an agent answers without settling the issue's disposition:
 * Paperclip ran it three times, could not classify the result, escalated to a
 * recovery owner, and then stopped dispatching entirely. Re-triggering did
 * nothing — four heartbeats reported success and sent no request.
 *
 * So the adapter's job is not "produce an answer". It is "leave the issue in a
 * state a human or the scheduler can act on". These tests pin that.
 */
describe("resolveDisposition", () => {
  it("sends a substantive answer to review", () => {
    const d = resolveDisposition("Dify and Suna forbid it; n8n forbids resale. Paperclip is MIT.");
    expect(d.status).toBe("in_review");
    expect(d.comment).toStartWith("Dify and Suna");
  });

  it("blocks rather than reviewing when the model declines", () => {
    const d = resolveDisposition(
      "I cannot answer this question because no evidence was provided. Please provide the evidence.",
    );
    expect(d.status).toBe("blocked");
    expect(d.comment).toContain("could not complete this task");
  });

  it("blocks on an empty answer instead of moving the task", () => {
    const d = resolveDisposition("   ");
    expect(d.status).toBe("blocked");
  });

  it("keeps the model's own words in the blocked comment, so a human can judge", () => {
    const d = resolveDisposition("I don't have access to the repository.");
    expect(d.comment).toContain("I don't have access to the repository.");
  });

  /**
   * Our own product name ends in "I". Substring matching turned
   * "NUFI cannot white-label Dify" into a refusal and filed a correct answer as
   * the agent giving up — seen on a real run, not imagined.
   */
  it("does not read the brand name as a refusal", () => {
    const answer =
      "NUFI cannot white-label the following projects due to their clauses: Dify forbids removing the logo; Suna forbids obscuring notices.";
    expect(resolveDisposition(answer).status).toBe("in_review");
  });

  it("still catches a real refusal that opens with the same words", () => {
    expect(resolveDisposition("I cannot answer without the document.").status).toBe("blocked");
  });

  it("does not treat a long answer that merely mentions 'cannot' as a refusal", () => {
    const answer =
      "The licence cannot be changed retroactively, so Dify remains unusable for white-labelling. " +
      "Suna is Elastic 2.0 and n8n is SUL. Only Paperclip, being MIT, permits a rebranded fork.";
    expect(resolveDisposition(answer).status).toBe("in_review");
  });
});

describe("buildPrompt", () => {
  it("leads with the company goal, which is what the hierarchy exists for", () => {
    const p = buildPrompt({
      goal: "Ship the agent app",
      title: "Draft the approvals page",
      description: "Cover what a review gate is.",
    });
    expect(p).toStartWith("Company goal: Ship the agent app");
    expect(p).toContain("Task: Draft the approvals page");
    expect(p).toContain("Cover what a review gate is.");
  });

  it("omits the goal line when there is no goal", () => {
    const p = buildPrompt({ goal: null, title: "T", description: "D" });
    expect(p).not.toContain("Company goal");
    expect(p).toStartWith("Task: T");
  });

  it("refuses to build a prompt from a title alone", () => {
    expect(() => buildPrompt({ goal: null, title: "T", description: "" })).toThrow(
      /no description/,
    );
  });
});
