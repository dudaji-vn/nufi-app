export const type = "nufi_agent";
export const label = "NUFI Works";

/**
 * The dropdown a person picks from when hiring one of these agents, and the
 * reason `gemini` is not in it.
 *
 * `gemini` is a working model on the gateway and it will not work here. The
 * gateway's G1 prompt-injection control classifies a tool result as
 * `untrusted` — threshold 0.50, one detector, no corroboration — and the
 * classifier scores benign text near 1.0, so every agent turn after the first
 * is refused. Measured on the smallest tool result that exists, `{"ok":true}`:
 * blocked as `role: tool`, fine as `role: user`.
 *
 * `nufi-agent` resolves to the same backend and is the one model name G1
 * exempts. Offering `gemini` here cost a full gate test: three agents were
 * hired against it, and all four of their tasks failed on the second turn.
 */
export const models = [
  { id: "nufi-agent", label: "NUFI agent model (Gemini, via the NUFI gateway)" },
];

export const agentConfigurationDoc = `# nufi_agent configuration

Use when: the employee should be a NUFI knowledge agent — a model reached
through the NUFI gateway, or an agent defined in NUFI chat with its tools, MCP
and RAG over company documents.

Don't use when: the work is editing a repository. Use claude_local or
codex_local, which run a coding harness in a sandbox with a git workspace.

Core fields:
  target        "gateway" (default) or "chat"
  gatewayUrl    gateway base ending in /v1 (default https://api.codechi.me/v1)
  model         model alias at the gateway (default "gemini")
  chatUrl       NUFI chat base URL, when target is "chat"
  chatAgentId   agent id in NUFI chat, when target is "chat"
  apiKeyEnv     NAME of the env var holding the model key (default
                NUFI_MODEL_API_KEY). Never the key itself — adapter config is
                visible in the UI.

Credential: the adapter reads that name from the agent's resolved env first and
the server's process env second. The normal setup is per member — bind
NUFI_MODEL_API_KEY on this agent as a user secret, and each person connects
their own NUFI account under Settings → NUFI. Runs then bill the member who
owns the work, and revoking one person changes nothing for anyone else.
  maxTokens     default 4096. Do not set this low: the model spends its
                reasoning budget before emitting text, so a small cap returns
                an empty answer rather than an error, and the run is then
                blocked for the wrong reason.

Every call goes to the NUFI gateway, where the guardrails run. Measured on the
live gateway: prompt injection is refused with HTTP 400 and a
nufi_guardrail_blocked reference.
`;

export { createServerAdapter } from "./server/index.js";
