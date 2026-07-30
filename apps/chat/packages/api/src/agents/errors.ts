import { ErrorTypes } from 'librechat-data-provider';

/**
 * Leading HTTP status code that provider SDKs prepend to `err.message`
 * (e.g. `400 This request was blocked by a security policy...`). The status is
 * already carried by the transport; repeating it in front of a sentence written
 * for a human is noise.
 */
const LEADING_HTTP_STATUS = /^\s*[1-5]\d{2}\s+/;

/**
 * Audit reference the security gateway appends to a refusal. It is the only handle a
 * blocked user has for asking support what happened, and the gateway carries it inside
 * the message rather than in a field of its own — the OpenAI error body has no room for
 * a fifth key.
 */
const GUARDRAIL_REFERENCE = /grd_[a-z0-9]+/i;

/** Shown only when the underlying error carries nothing a user can act on. */
export const GENERIC_RUN_ERROR = 'An error occurred while processing the request';

/**
 * User-facing text for an error that aborted an agent run.
 *
 * Upstream refusals (security policy blocks, content filters, quota notices)
 * arrive as complete sentences addressed to the user and often carry the only
 * copy of a reference id. Prefixing them with a generic wrapper buries that
 * signal — and, because the renderer truncates at 512 characters, a long enough
 * prefix can push a trailing reference id off the end entirely. So a usable
 * message is surfaced on its own, and the wrapper is kept only when there is
 * nothing else to show.
 */
export function formatRunErrorText(message?: string | null): string {
  if (typeof message !== 'string') {
    return GENERIC_RUN_ERROR;
  }

  const detail = message.replace(LEADING_HTTP_STATUS, '').trim();
  if (!detail) {
    return GENERIC_RUN_ERROR;
  }

  return detail;
}

/**
 * Error body the security gateway puts on the wire, as the OpenAI SDK exposes it: the
 * fields are hoisted onto the thrown error and the parsed body is kept under `error`.
 */
interface GuardrailErrorBody {
  type?: string;
  param?: string;
  message?: string;
  error?: GuardrailErrorBody;
}

/** Structured refusal handed to the client, which selects its copy from `risk`. */
export interface GuardrailBlockedPayload {
  type: ErrorTypes.GUARDRAIL_BLOCKED;
  risk?: string;
  reference?: string;
}

function readBody(err: unknown): GuardrailErrorBody | undefined {
  if (err == null || typeof err !== 'object') {
    return undefined;
  }
  return err as GuardrailErrorBody;
}

function firstString(...values: (string | undefined)[]): string | undefined {
  return values.find((value) => typeof value === 'string' && value.length > 0);
}

/**
 * Recognises a security-gateway refusal and restates it as structured data.
 *
 * The gateway marks a block with `type: "nufi_guardrail_blocked"` and the OWASP risk
 * code in `param`. Both survive the OpenAI SDK intact — on the error itself and again
 * on the parsed `error` body — so the discriminator is read, never inferred from the
 * prose. Returns `undefined` for anything else, which keeps every genuine failure on
 * the plain-text path.
 */
export function toGuardrailBlockedPayload(err: unknown): GuardrailBlockedPayload | undefined {
  const error = readBody(err);
  const body = readBody(error?.error);

  if (firstString(error?.type, body?.type) !== ErrorTypes.GUARDRAIL_BLOCKED) {
    return undefined;
  }

  const message = firstString(body?.message, error?.message);
  return {
    type: ErrorTypes.GUARDRAIL_BLOCKED,
    risk: firstString(error?.param, body?.param),
    reference: message?.match(GUARDRAIL_REFERENCE)?.[0],
  };
}

/**
 * Content-part text for an error that aborted an agent run.
 *
 * A policy refusal is the system working, so it is emitted as a typed JSON payload the
 * renderer can frame as a decision instead of a malfunction — the same convention the
 * rest of the codebase uses for typed errors. Everything else stays plain text and
 * keeps the generic error framing it has always had.
 */
export function formatRunError(err: unknown): string {
  const blocked = toGuardrailBlockedPayload(err);
  if (blocked) {
    return JSON.stringify(blocked);
  }

  return formatRunErrorText(readBody(err)?.message);
}
