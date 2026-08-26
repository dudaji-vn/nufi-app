const API_URL = process.env.PAPERCLIP_API_URL ?? "http://localhost:3100";
const API_KEY = process.env.PAPERCLIP_API_KEY ?? "";

/**
 * Every mutating call carries X-Paperclip-Run-Id. The control plane requires it
 * to link an action to the heartbeat that caused it; without it the audit trail
 * has a hole exactly where an agent changed something.
 */
function headers(runId?: string) {
  const h: Record<string, string> = {
    "content-type": "application/json",
    authorization: `Bearer ${API_KEY}`,
  };
  if (runId) h["X-Paperclip-Run-Id"] = runId;
  return h;
}

export interface IssueContext {
  title: string;
  description: string;
  goal: string | null;
}

/**
 * Exported so it can be tested against a real captured response rather than an
 * assumed shape. The assumption is what broke it the first time.
 */
export function parseHeartbeatContext(raw: unknown): IssueContext {
  const data = raw as {
    issue?: { title?: string; description?: string };
    goal?: { title?: string } | null;
  };

  const title = data.issue?.title ?? "";
  const description = data.issue?.description ?? "";

  if (!description) {
    throw new Error(
      `heartbeat-context returned no description for "${title}" — refusing to prompt on a title alone`,
    );
  }

  return { title, description, goal: data.goal?.title ?? null };
}

export const paperclip = {
  async checkout(issueId: string, agentId: string, runId: string) {
    const res = await fetch(`${API_URL}/api/issues/${issueId}/checkout`, {
      method: "POST",
      headers: headers(runId),
      body: JSON.stringify({
        agentId,
        expectedStatuses: ["todo", "backlog", "blocked", "in_review"],
      }),
    });
    if (res.status === 409) return { ok: false, conflict: true };
    return { ok: res.ok };
  },

  /**
   * The field is `description`, not `body`. Reading `body` yields undefined and
   * the agent receives a title with no detail — which does not fail, it
   * fabricates. Measured: given only "Summarise what the NUFI agent-app design
   * decided", the model invented a non-custodial crypto product and said so
   * confidently. A silently empty prompt is the worst shape this can fail in,
   * so `parseHeartbeatContext` asserts the field is there.
   *
   * `goal` is included because it is the whole point of Paperclip's model —
   * every task traces to the company goal, and an agent that cannot see the
   * goal cannot honour it.
   */
  async heartbeatContext(issueId: string) {
    const res = await fetch(`${API_URL}/api/issues/${issueId}/heartbeat-context`, {
      headers: headers(),
    });
    if (!res.ok) throw new Error(`heartbeat-context ${res.status}`);
    return parseHeartbeatContext(await res.json());
  },

  async comment(issueId: string, body: string, runId: string) {
    const res = await fetch(`${API_URL}/api/issues/${issueId}/comments`, {
      method: "POST",
      headers: headers(runId),
      body: JSON.stringify({ body }),
    });
    if (!res.ok) throw new Error(`comment ${res.status}`);
  },

  async setStatus(issueId: string, status: string, runId: string) {
    const res = await fetch(`${API_URL}/api/issues/${issueId}`, {
      method: "PATCH",
      headers: headers(runId),
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error(`status ${res.status}`);
  },
};
