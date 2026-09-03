import { describe, expect, it } from "bun:test";

import { systemPrompt, wakeMessage } from "./prompt";

describe("wakeMessage", () => {
  /**
   * The task text rides in the wake, exactly as Paperclip's own
   * `PAPERCLIP_WAKE_PAYLOAD_JSON` does — "it contains the compact issue summary
   * … Use it first."
   *
   * This is not only fidelity. The gateway's G1 control classifies a `tool`
   * message as `untrusted`, where a single detector blocks the whole request;
   * a `user` message needs two detectors to agree. Measured on LEG-8, the
   * classifier scored 0.99999 on an ordinary HR leave policy delivered as a
   * tool result and killed the run, while the regex detector saw nothing. The
   * same text delivered in the wake is corroborated content and survives.
   */
  it("carries the task so the agent does not have to fetch it", () => {
    const text = wakeMessage({
      issueId: "issue_1",
      companyId: "co_1",
      agentId: "agent_1",
      issue: {
        title: "Review the termination clause",
        description: "Clause 12.2 keeps us liable for the remainder of the term.",
        status: "todo",
        priority: "high",
        goal: "Cut vendor risk",
      },
    });

    expect(text).toContain("Review the termination clause");
    expect(text).toContain("Clause 12.2");
    expect(text).toContain("Cut vendor risk");
    expect(text).toContain("high");
  });

  /** A task with no description must read as missing, not as an empty string. */
  it("says plainly when the task has no description", () => {
    const text = wakeMessage({
      issueId: "issue_1",
      companyId: "co_1",
      agentId: "agent_1",
      issue: { title: "test 1", description: "", status: "todo" },
    });

    expect(text).toMatch(/no description/i);
  });

  it("still works when the task could not be prefetched", () => {
    const text = wakeMessage({ issueId: "issue_1", companyId: "co_1", agentId: "agent_1" });

    expect(text).toContain("issue_1");
    expect(text).toMatch(/get_issue/);
  });

  it("passes the wake reason and the comment that caused it", () => {
    const text = wakeMessage({
      issueId: "issue_1",
      companyId: "co_1",
      agentId: "agent_1",
      wakeReason: "issue_commented",
      wakeCommentId: "cmt_7",
    });

    expect(text).toContain("issue_commented");
    expect(text).toContain("cmt_7");
  });
});

describe("systemPrompt", () => {
  /** Rule number one, verbatim from Paperclip's own skill. */
  it("carries the rule that separates an agent from a chatbot", () => {
    expect(systemPrompt()).toMatch(/NEVER ASK A PERSON TO DO WHAT AN AGENT COULD DO/);
  });

  /** The measured failure this whole design exists to prevent. */
  it("forbids reporting work that no tool call performed", () => {
    const text = systemPrompt();
    expect(text).toMatch(/DID NOT HAPPEN/);
    expect(text).toMatch(/unless a\s+tool call returned ok/);
  });

  it("tells the agent to claim the task before working it", () => {
    expect(systemPrompt()).toMatch(/checkout_issue/);
  });
});
