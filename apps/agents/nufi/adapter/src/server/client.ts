import type { ExecuteDeps, ExecutionContext } from "./execute.js";

/**
 * The live wiring: Paperclip's control plane on one side, the NuFi model
 * endpoint on the other.
 *
 * Both halves are built per-run because the credentials are per-run:
 * `ctx.authToken` is a short-lived run JWT, and the model key comes from an env
 * var named in adapter config — never stored in the config itself, which is
 * visible in the UI.
 */

interface NufiConfig {
  /** "gateway" (default) or "chat". */
  target?: string;
  /** Gateway base, ending in /v1. */
  gatewayUrl?: string;
  /** Model alias at the gateway. */
  model?: string;
  /** apps/chat base URL, when target is "chat". */
  chatUrl?: string;
  /** Agent id in apps/chat, when target is "chat". */
  chatAgentId?: string;
  /** Name of the env var holding the key. NOT the key. */
  apiKeyEnv?: string;
  maxTokens?: number;
}

function str(v: unknown, fallback: string): string {
  return typeof v === "string" && v.trim() ? v.trim() : fallback;
}

export function buildDeps(ctx: ExecutionContext): ExecuteDeps {
  const cfg = ctx.config as NufiConfig;

  const apiUrl = str(process.env.PAPERCLIP_API_URL, "http://localhost:3100");
  const runToken = ctx.authToken ?? process.env.PAPERCLIP_API_KEY ?? "";

  const target = str(cfg.target, "gateway");
  const keyEnv = str(cfg.apiKeyEnv, "NUFI_MODEL_API_KEY");
  const modelKey = process.env[keyEnv] ?? "";

  /**
   * Generous by default. Gemini spends its reasoning budget before emitting
   * text — measured, a 20-token cap returned empty content with 15 tokens gone
   * to reasoning, and no error. A small cap looks like a refusal rather than a
   * truncation, and `resolveDisposition` would then block the issue for the
   * wrong reason.
   */
  const maxTokens = typeof cfg.maxTokens === "number" ? cfg.maxTokens : 4096;

  const modelEndpoint =
    target === "chat"
      ? `${str(cfg.chatUrl, "http://localhost:3080")}/api/agents/chat/completions`
      : `${str(cfg.gatewayUrl, "https://api.codechi.me/v1")}/chat/completions`;

  const modelName = target === "chat" ? str(cfg.chatAgentId, "") : str(cfg.model, "gemini");

  /** Every mutating call carries the run id, or the audit trail loses the link. */
  const pcHeaders = {
    "content-type": "application/json",
    authorization: `Bearer ${runToken}`,
    "X-Paperclip-Run-Id": ctx.runId,
  };

  return {
    async fetchIssue(issueId) {
      const res = await fetch(`${apiUrl}/api/issues/${issueId}/heartbeat-context`, {
        headers: pcHeaders,
      });
      if (!res.ok) throw new Error(`heartbeat-context ${res.status}`);

      const data = (await res.json()) as {
        issue?: { title?: string; description?: string; status?: string };
        goal?: { title?: string } | null;
      };
      // `description`, not `body` — see disposition.ts and the spike findings.
      return {
        title: data.issue?.title ?? "",
        description: data.issue?.description ?? "",
        goal: data.goal?.title ?? null,
        status: data.issue?.status ?? "todo",
      };
    },

    async complete(prompt) {
      if (!modelKey) throw new Error(`${keyEnv} is not set — no credential to call the model with`);
      if (target === "chat" && !modelName) throw new Error("chatAgentId is required when target is chat");

      const res = await fetch(modelEndpoint, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${modelKey}` },
        body: JSON.stringify({
          model: modelName,
          messages: [{ role: "user", content: prompt }],
          max_tokens: maxTokens,
          stream: false,
        }),
      });
      if (!res.ok) throw new Error(`${target} ${res.status}: ${(await res.text()).slice(0, 300)}`);

      const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
      return data.choices?.[0]?.message?.content ?? "";
    },

    async comment(issueId, body) {
      const res = await fetch(`${apiUrl}/api/issues/${issueId}/comments`, {
        method: "POST",
        headers: pcHeaders,
        body: JSON.stringify({ body }),
      });
      if (!res.ok) throw new Error(`comment ${res.status}`);
    },

    async lastComment(issueId) {
      const res = await fetch(`${apiUrl}/api/issues/${issueId}/comments`, { headers: pcHeaders });
      if (!res.ok) return null;
      const raw = (await res.json()) as unknown;
      const list = (Array.isArray(raw) ? raw : ((raw as { comments?: unknown[] }).comments ?? [])) as {
        body?: string;
        createdAt?: string;
      }[];
      if (list.length === 0) return null;
      // The API returns newest first; fall back to sorting if that ever changes.
      const newest = list[0]?.createdAt
        ? [...list].sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)))[0]
        : list[0];
      return newest?.body ?? null;
    },

    async setStatus(issueId, status) {
      const res = await fetch(`${apiUrl}/api/issues/${issueId}`, {
        method: "PATCH",
        headers: pcHeaders,
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error(`status ${res.status}`);
    },
  };
}
