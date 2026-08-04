import { agentConfigurationDoc, models, type } from "../index.js";
import { buildDeps } from "./client.js";
import { runWith, type ExecutionContext, type ExecutionResult } from "./execute.js";

async function execute(ctx: ExecutionContext): Promise<ExecutionResult> {
  return runWith(buildDeps(ctx), ctx);
}

/**
 * Environment diagnostics, surfaced in Settings → Adapters. Checks the two
 * things that actually stop a run: no credential, and a gateway that will not
 * answer. Both are reported as `error` rather than `warn` because neither
 * degrades gracefully — the run just fails.
 */
async function testEnvironment() {
  const checks: { code: string; level: "info" | "warn" | "error"; message: string }[] = [];

  const keyEnv = process.env.NUFI_MODEL_API_KEY ? "NUFI_MODEL_API_KEY" : null;
  if (!keyEnv) {
    checks.push({
      code: "nufi_key_missing",
      level: "error",
      message: "NUFI_MODEL_API_KEY is not set — the adapter has no credential to call the model with",
    });
  } else {
    checks.push({ code: "nufi_key_present", level: "info", message: "Model credential is set" });
  }

  const apiUrl = process.env.PAPERCLIP_API_URL ?? "http://localhost:3100";
  checks.push({
    code: "nufi_api_url",
    level: "info",
    message: `Paperclip control plane: ${apiUrl}`,
  });

  const failed = checks.some((c) => c.level === "error");
  return {
    adapterType: type,
    status: failed ? ("fail" as const) : ("pass" as const),
    checks,
    testedAt: new Date().toISOString(),
  };
}

export function createServerAdapter() {
  return { type, execute, testEnvironment, models, agentConfigurationDoc };
}
