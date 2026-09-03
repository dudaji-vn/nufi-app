import { agentConfigurationDoc, models, type } from "../index.js";
import { buildDeps } from "./client.js";
import { runWith, type ExecutionContext, type ExecutionResult } from "./execute.js";

async function execute(ctx: ExecutionContext): Promise<ExecutionResult> {
  return runWith(buildDeps(ctx), ctx);
}

/**
 * Environment diagnostics, surfaced in Settings → Adapters.
 *
 * This runs with no run context, so it can see the server's process env and
 * nothing else. Since a per-member secret bound to an agent also satisfies the
 * credential — and is the preferred path — a missing process env is reported as
 * `warn`, not `error`. Calling it fatal would mark a correctly configured
 * install as broken, which is worse than under-reporting: the run itself still
 * fails loudly, naming both ways to fix it.
 */
async function testEnvironment() {
  const checks: {
    code: string;
    level: "info" | "warn" | "error";
    message: string;
    detail?: string;
  }[] = [];

  if (process.env.NUFI_MODEL_API_KEY) {
    checks.push({
      code: "nufi_key_present",
      level: "info",
      message: "Server-wide model credential is set (NUFI_MODEL_API_KEY)",
    });
  } else {
    checks.push({
      code: "nufi_key_missing",
      level: "warn",
      message: "No server-wide NUFI_MODEL_API_KEY",
      detail:
        "Runs will use each member's own gateway key, bound to the agent as the NUFI_MODEL_API_KEY secret. " +
        "Members connect theirs under Settings → NUFI. A member who has not connected cannot run this agent.",
    });
  }

  const apiUrl = process.env.PAPERCLIP_API_URL ?? "http://localhost:3100";
  checks.push({
    code: "nufi_api_url",
    level: "info",
    message: `Paperclip control plane: ${apiUrl}`,
  });

  const failed = checks.some((c) => c.level === "error");
  const warned = checks.some((c) => c.level === "warn");
  return {
    adapterType: type,
    status: failed ? ("fail" as const) : warned ? ("warn" as const) : ("pass" as const),
    checks,
    testedAt: new Date().toISOString(),
  };
}

export function createServerAdapter() {
  return {
    type,
    execute,
    testEnvironment,
    models,
    agentConfigurationDoc,
    /**
     * Ask the control plane to mint a run JWT and hand it to us as
     * `ctx.authToken`. Every call this adapter makes back to Paperclip — read
     * the issue, comment, set the status — is authorized by it.
     *
     * Omitting this does not produce an auth error, which is why it survived
     * review: an actor with no token has access to no company, and the issue
     * routes answer "not accessible" and "does not exist" with the same 404 so
     * that ids cannot be probed across tenants. The run then reports
     * `heartbeat-context 404` about an issue sitting right there in the UI.
     *
     * It is also invisible locally: `local_trusted` mode treats every caller as
     * a trusted board, so the tokenless adapter works on a laptop and fails on
     * every authenticated deployment.
     */
    supportsLocalAgentJwt: true,
  };
}
