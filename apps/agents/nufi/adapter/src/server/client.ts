import type { ExecutionContext } from "./execute.js";
import type { LoopModel, ToolCall } from "./loop.js";
import type { HttpFn } from "./tools.js";

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

/**
 * The live wiring: Paperclip's control plane on one side, the NuFi model
 * endpoint on the other. Both halves are built per run because the credentials
 * are per run — `ctx.authToken` is a short-lived run JWT, and the model key
 * comes from an env var named in adapter config.
 */
export function buildHttp(ctx: ExecutionContext): HttpFn {
  const apiUrl = str(process.env.PAPERCLIP_API_URL, "http://localhost:3100");
  const runToken = ctx.authToken ?? process.env.PAPERCLIP_API_KEY ?? "";

  return async ({ method, path, headers, body }) => {
    const res = await fetch(`${apiUrl}${path}`, {
      method,
      headers: { ...headers, authorization: `Bearer ${requireRunToken(runToken)}` },
      ...(body === undefined || method === "GET" ? {} : { body: JSON.stringify(body) }),
    });
    const text = await res.text();
    let parsed: unknown = text;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      /* a non-JSON body is still worth handing back verbatim */
    }
    return { status: res.status, body: parsed };
  };
}

/**
 * One model turn, in the OpenAI tool-calling shape.
 *
 * Verified against the live NUFI gateway before this was written: a
 * `/v1/chat/completions` request carrying `tools` comes back with
 * `finish_reason: "tool_calls"` and well-formed arguments, so nothing here is
 * speculative about what the gateway supports.
 */
/**
 * Whether a gateway refusal is worth trying again.
 *
 * The NUFI gateway fails closed when a guardrail cannot run: it answers 503
 * `GUARDRAIL_UNAVAILABLE` and says, in the body, "This is usually temporary —
 * please retry." Observed twice while this loop was being built, both times
 * mid-run after several turns had already succeeded, and never reproducible on
 * demand — 12/12 short requests and 8/8 full-size ones passed straight after.
 *
 * Retrying is right here and nowhere near it. A refusal that names a policy —
 * `LLM01_INJECTION` and its kin — is a decision, and hammering it would be
 * arguing with the security stack. Only "the check could not run" is retried.
 */
export function shouldRetryGateway(status: number, body: string): boolean {
  if (status !== 503) return false;
  return body.includes("GUARDRAIL_UNAVAILABLE");
}

/**
 * Backoff, not a fixed pause.
 *
 * The guardrail's unavailable windows are short but longer than one breath.
 * Measured: three attempts 1.5s apart all landed inside a single window and the
 * run died, while eight consecutive requests before and after it passed. These
 * delays cover about seventeen seconds — nothing against a heartbeat that
 * already spends twenty-five on the model.
 */
const GATEWAY_RETRY_DELAYS_MS = [2000, 5000, 10000];

export function buildModel(ctx: ExecutionContext): LoopModel {
  const cfg = ctx.config as NufiConfig;
  const keyEnv = str(cfg.apiKeyEnv, "NUFI_MODEL_API_KEY");
  const modelKey = resolveModelKey(cfg, keyEnv, process.env);
  const endpoint = `${str(cfg.gatewayUrl, "https://api.codechi.me/v1")}/chat/completions`;
  const model = str(cfg.model, "gemini");

  /**
   * Generous on purpose. Gemini spends its reasoning budget before emitting
   * text — measured on the gateway, `gemini-2.5-pro` burned 148 output tokens
   * to answer "OK", and a 64-token cap returned empty content with no error at
   * all. A small cap here reads as a refusal rather than a truncation.
   */
  const maxTokens = typeof cfg.maxTokens === "number" ? cfg.maxTokens : 4096;

  return {
    async turn(messages, tools) {
      if (!modelKey) {
        throw new Error(
          `${keyEnv} is not set — no credential to call the model with. ` +
            `Connect your NUFI account under Settings → NUFI, or set ${keyEnv} on the server.`,
        );
      }

      const payload = JSON.stringify({
          model,
          messages,
          max_tokens: maxTokens,
          stream: false,
          ...(tools.length
            ? {
                tools: tools.map((t) => ({
                  type: "function",
                  function: { name: t.name, description: t.description, parameters: t.parameters },
                })),
                tool_choice: "auto",
              }
            : {}),
      });

      let res: Response | null = null;
      let failure = "";
      for (let attempt = 0; attempt <= GATEWAY_RETRY_DELAYS_MS.length; attempt += 1) {
        res = await fetch(endpoint, {
          method: "POST",
          headers: { "content-type": "application/json", authorization: `Bearer ${modelKey}` },
          body: payload,
        });
        if (res.ok) break;
        failure = (await res.text()).slice(0, 300);
        if (!shouldRetryGateway(res.status, failure) || attempt === GATEWAY_RETRY_DELAYS_MS.length) {
          throw new Error(`gateway ${res.status}: ${failure}`);
        }
        await new Promise((resolve) => setTimeout(resolve, GATEWAY_RETRY_DELAYS_MS[attempt]));
      }

      const data = (await res!.json()) as {
        choices?: {
          message?: {
            content?: string | null;
            tool_calls?: { id?: string; function?: { name?: string; arguments?: string } }[];
          };
        }[];
      };
      const message = data.choices?.[0]?.message ?? {};
      const toolCalls: ToolCall[] = (message.tool_calls ?? []).map((call, index) => ({
        id: call.id ?? `call_${index}`,
        name: call.function?.name ?? "",
        // The gateway hands arguments back as a JSON string. A model that emits
        // malformed JSON must reach the tool as an empty object rather than
        // crashing the run — the tool will refuse it and say why.
        arguments: parseArguments(call.function?.arguments),
      }));

      return { text: message.content ?? "", toolCalls };
    },
  };
}

function parseArguments(raw: string | undefined): unknown {
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    return {};
  }
}
