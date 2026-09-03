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
  /**
   * Environment bindings, already resolved by the control plane.
   *
   * Paperclip resolves an agent's env bindings before dispatch and merges the
   * result into the adapter config it passes here. A `user_secret_ref` binding
   * resolves against the run's responsible user, so this is how one agent hands
   * each member their own gateway key.
   *
   * Typed `unknown` because it crosses a process boundary as JSON.
   */
  env?: unknown;
}

function str(v: unknown, fallback: string): string {
  return typeof v === "string" && v.trim() ? v.trim() : fallback;
}

/**
 * Where the gateway credential comes from, in priority order.
 *
 * 1. `config.env` — a secret bound to this agent and resolved by the control
 *    plane. With a `user_secret_ref` binding this is the running member's own
 *    key, which is what makes per-user attribution and per-user budgets real
 *    rather than a label on one shared key.
 * 2. `process.env` — the deploy-time key. Still the right answer for a
 *    single-tenant or air-gapped install; no longer the only one.
 *
 * A blank bound value falls through rather than winning. Paperclip writes
 * `env: {}` whenever an agent has an env block at all, so "present but empty"
 * is the ordinary shape of unconfigured — not an instruction to use no key.
 */
export function resolveModelKey(
  config: { env?: unknown },
  keyEnv: string,
  processEnv: Record<string, string | undefined>,
): string {
  const bound = config.env;
  if (bound && typeof bound === "object" && !Array.isArray(bound)) {
    const value = (bound as Record<string, unknown>)[keyEnv];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return processEnv[keyEnv]?.trim() ?? "";
}

/**
 * Refuse to call the control plane without a run token.
 *
 * Paperclip does not answer an unauthenticated call with 401. An actor with no
 * token has access to no company, and the issue routes deliberately return the
 * same 404 for "does not exist" and "exists in another tenant" so ids cannot be
 * enumerated. A tokenless adapter therefore reports `heartbeat-context 404` —
 * which reads as "someone deleted the issue" and sends the reader looking in
 * entirely the wrong place. Observed exactly that way in production.
 *
 * Fail here instead, while the cause is still legible.
 */
export function requireRunToken(token: string): string {
  if (!token.trim()) {
    throw new Error(
      "No Paperclip run token. The control plane mints one only for adapters that " +
        "declare supportsLocalAgentJwt, and PAPERCLIP_API_KEY is not set as a fallback. " +
        "Without it every control-plane call returns 404 rather than an auth error.",
    );
  }
  return token;
}

export function buildDeps(ctx: ExecutionContext): ExecuteDeps {
  const cfg = ctx.config as NufiConfig;

  const apiUrl = str(process.env.PAPERCLIP_API_URL, "http://localhost:3100");
  const runToken = ctx.authToken ?? process.env.PAPERCLIP_API_KEY ?? "";

  const target = str(cfg.target, "gateway");
  const keyEnv = str(cfg.apiKeyEnv, "NUFI_MODEL_API_KEY");
  const modelKey = resolveModelKey(cfg, keyEnv, process.env);

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
  const pcHeaders = () => ({
    "content-type": "application/json",
    authorization: `Bearer ${requireRunToken(runToken)}`,
    "X-Paperclip-Run-Id": ctx.runId,
  });

  return {
    async fetchIssue(issueId) {
      const res = await fetch(`${apiUrl}/api/issues/${issueId}/heartbeat-context`, {
        headers: pcHeaders(),
      });
      if (!res.ok) throw new Error(`heartbeat-context ${res.status}`);

      const data = (await res.json()) as {
        issue?: { title?: string; description?: string; status?: string; assigneeUserId?: string | null };
        goal?: { title?: string } | null;
      };
      // `description`, not `body` — see disposition.ts and the spike findings.
      const assignee = data.issue?.assigneeUserId;
      return {
        title: data.issue?.title ?? "",
        description: data.issue?.description ?? "",
        goal: data.goal?.title ?? null,
        status: data.issue?.status ?? "todo",
        assigneeUserId: typeof assignee === "string" && assignee.trim() ? assignee.trim() : null,
      };
    },

    async complete(prompt) {
      if (!modelKey)
        throw new Error(
          `${keyEnv} is not set — no credential to call the model with. ` +
            `Connect your NUFI account under Settings → NUFI, or set ${keyEnv} on the server.`,
        );
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
        headers: pcHeaders(),
        body: JSON.stringify({ body }),
      });
      if (!res.ok) throw new Error(`comment ${res.status}`);
    },

    async lastComment(issueId) {
      const res = await fetch(`${apiUrl}/api/issues/${issueId}/comments`, { headers: pcHeaders() });
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

    async setStatus(issueId, status, handoff) {
      const res = await fetch(`${apiUrl}/api/issues/${issueId}`, {
        method: "PATCH",
        headers: pcHeaders(),
        body: JSON.stringify({ status, ...(handoff ?? {}) }),
      });
      /**
       * The body matters here. A bare `status 422` sent the last diagnosis to
       * the wrong place entirely: the server explains exactly which review path
       * is missing, and throwing that away turned an actionable refusal into a
       * number. Keep enough of it to act on.
       */
      if (!res.ok) throw new Error(`status ${res.status}: ${(await res.text()).slice(0, 300)}`);
    },
  };
}
