import { describe, expect, it } from "bun:test";

import { parseHeartbeatContext } from "./paperclip";

/**
 * Captured from a real `GET /api/issues/:id/heartbeat-context` against a running
 * server, trimmed to the fields this code reads. Written against a captured
 * response rather than an assumed shape, because assuming the shape is what
 * broke it: the field is `description`, and reading `body` yielded undefined.
 * The agent then received a title with no detail and fabricated an answer —
 * silently, and confidently.
 */
const REAL_RESPONSE = {
  issue: {
    id: "9d46a023-41da-4fa9-8239-111c7f84fbd4",
    identifier: "NSC-2",
    title: "Which licences forbid white-labelling, given this evidence",
    description: "Evidence, verbatim from each project's LICENSE:\n- Dify: …",
    status: "todo",
    priority: "high",
  },
  ancestors: [],
  project: null,
  goal: { title: "Answer whether Paperclip's model suits NuFi users." },
  commentCursor: null,
};

describe("parseHeartbeatContext", () => {
  it("reads description, not body", () => {
    const ctx = parseHeartbeatContext(REAL_RESPONSE);
    expect(ctx.description).toStartWith("Evidence, verbatim");
    expect(ctx.title).toBe("Which licences forbid white-labelling, given this evidence");
  });

  it("carries the company goal, which is what the task hierarchy exists for", () => {
    expect(parseHeartbeatContext(REAL_RESPONSE).goal).toBe(
      "Answer whether Paperclip's model suits NuFi users.",
    );
  });

  it("tolerates a missing goal", () => {
    const ctx = parseHeartbeatContext({ ...REAL_RESPONSE, goal: null });
    expect(ctx.goal).toBeNull();
  });

  it("throws rather than prompting on a title alone", () => {
    const noDescription = { ...REAL_RESPONSE, issue: { title: "Do the thing" } };
    expect(() => parseHeartbeatContext(noDescription)).toThrow(/no description/);
  });

  it("throws on the old wrong shape, so the regression cannot come back", () => {
    const wrongField = { issue: { title: "Do the thing", body: "the detail" } };
    expect(() => parseHeartbeatContext(wrongField)).toThrow(/no description/);
  });
});
