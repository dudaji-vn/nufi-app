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

describe("the answer a person gave", () => {
  /**
   * The last link in "ask → answer → continue".
   *
   * A person's answer to `ask_user_questions` or `request_confirmation` is
   * stored on the interaction row, in `result` — it is not a comment. So an
   * agent woken by that answer and told to "read the comment" finds nothing,
   * and asks again or blocks.
   *
   * Carrying it in the wake is the same shape as the prefetched task, and for
   * the same second reason: a `user` span needs two detectors to agree, where
   * a tool result needs only one to refuse the whole run.
   */
  it("puts the decision in the wake, where the agent will see it", () => {
    const text = wakeMessage({
      issueId: "issue_1",
      companyId: "co_1",
      agentId: "agent_1",
      wakeReason: "issue_commented",
      interaction: {
        kind: "ask_user_questions",
        status: "answered",
        title: "Procurement details needed",
        result: { laptop: "MacBook Pro 14, 32GB", budget: "under $3000" },
      },
      issue: null,
    });

    expect(text).toContain("Procurement details needed");
    expect(text).toContain("MacBook Pro 14, 32GB");
    expect(text).toMatch(/answered|decided/i);
  });

  it("says so when the person declined", () => {
    const text = wakeMessage({
      issueId: "issue_1",
      companyId: "co_1",
      agentId: "agent_1",
      interaction: { kind: "request_confirmation", status: "rejected", title: "Ship it?", result: null },
      issue: null,
    });

    expect(text).toContain("rejected");
    expect(text).toContain("Ship it?");
  });

  it("stays quiet when no interaction is involved", () => {
    const text = wakeMessage({ issueId: "issue_1", companyId: "co_1", agentId: "agent_1", issue: null });
    expect(text).not.toMatch(/interaction/i);
  });
});

describe("the rest of the board", () => {
  /**
   * A colleague joining a company can see the board. The agent could not, and
   * no amount of telling it to look fixed that.
   *
   * Measured twice on HAN-2/HAN-3, same task both times — "based on the offer
   * document from the previous task" — and both times
   * `tools used: checkout_issue, get_issue, ask_user_questions`. The second run
   * was after `list_issues` and `read_plan` shipped and the prompt said to
   * check them first. It still asked, because it had no reason to believe a
   * neighbouring task existed: an agent cannot look up what it does not know is
   * there.
   *
   * So the neighbours arrive with the wake, the same way the task itself does,
   * and for the same second reason — a `user` span rather than a tool result.
   */
  it("lists the neighbouring tasks so the agent knows they exist", () => {
    const text = wakeMessage({
      issueId: "issue_1",
      companyId: "co_1",
      agentId: "agent_1",
      issue: { title: "Draft the letter", description: "Build on the previous task.", status: "todo", priority: null, goal: null, project: null },
      neighbours: [
        { id: "issue_0", identifier: "HAN-1", title: "Open sales in Hai Phong", status: "in_review" },
        { id: "issue_9", identifier: "HAN-2", title: "Draft the letter", status: "in_progress" },
      ],
    });

    expect(text).toContain("HAN-1");
    expect(text).toContain("Open sales in Hai Phong");
    expect(text).toMatch(/read_plan/);
  });

  it("says nothing about the board when there is nothing else on it", () => {
    const text = wakeMessage({
      issueId: "issue_1",
      companyId: "co_1",
      agentId: "agent_1",
      issue: null,
      neighbours: [],
    });

    expect(text).not.toMatch(/other tasks/i);
  });
});

describe("which company this is", () => {
  /**
   * The agent asked a person to describe the company it works for.
   *
   * Measured on HAN-3, after it had correctly read the neighbouring task's
   * plan: `tools used: checkout_issue, list_issues, get_issue, read_plan,
   * ask_user_questions`, and the one thing it still asked for was "information
   * about Hanwoo Foods" — the mission written on the company record when the
   * company was created. `heartbeat-context` returns `company: null`, so it had
   * no way to know.
   *
   * A new hire is told what the company does on day one. This is that, and it
   * is the last thing in the wake that the agent was asking people for.
   */
  it("names the company and what it is for", () => {
    const text = wakeMessage({
      issueId: "issue_1",
      companyId: "co_1",
      agentId: "agent_1",
      company: { name: "Hanwoo Foods", mission: "Cung cấp thực phẩm chế biến sẵn cho chuỗi cửa hàng tiện lợi." },
      issue: null,
    });

    expect(text).toContain("Hanwoo Foods");
    expect(text).toContain("thực phẩm chế biến sẵn");
  });

  it("says nothing when the company could not be read", () => {
    const text = wakeMessage({ issueId: "issue_1", companyId: "co_1", agentId: "agent_1", issue: null });

    expect(text).not.toMatch(/## The company/);
  });
});


describe("a neighbour you can actually open", () => {
  /**
   * The list named the neighbours and left out the one thing needed to read
   * them.
   *
   * Measured on HAN-4: `tools used: checkout_issue, read_plan,
   * ask_user_questions`. It reached for read_plan — the right tool — but the
   * wake gave it "HAN-1" and read_plan takes an id, so it called read_plan with
   * no argument, got its own empty plan back, and asked "which task contains
   * this information?".
   *
   * A pointer you cannot follow is not a pointer.
   */
  it("gives each neighbour the id read_plan needs", () => {
    const text = wakeMessage({
      issueId: "issue_1",
      companyId: "co_1",
      agentId: "agent_1",
      issue: null,
      neighbours: [{ id: "issue_0", identifier: "HAN-1", title: "Open sales", status: "done" }],
    });

    expect(text).toContain("issue_0");
    expect(text).toContain("HAN-1");
  });
});
