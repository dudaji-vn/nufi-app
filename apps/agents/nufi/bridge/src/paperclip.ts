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

  async heartbeatContext(issueId: string) {
    const res = await fetch(`${API_URL}/api/issues/${issueId}/heartbeat-context`, {
      headers: headers(),
    });
    if (!res.ok) throw new Error(`heartbeat-context ${res.status}`);
    const data = (await res.json()) as { issue?: { title?: string; body?: string } };
    return { title: data.issue?.title ?? "", body: data.issue?.body ?? "" };
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
