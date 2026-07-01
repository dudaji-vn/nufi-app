const { createAuditLog } = require('~/models');

/** Guardrail event type → audit action key. */
const ACTION_BY_TYPE = {
  injection: 'guardrail_injection_blocked',
  pii_input: 'guardrail_pii_input_blocked',
  pii_output: 'guardrail_pii_output_redacted',
};

/** "2 email, 1 phone" from { email: 2, phone: 1 }. */
function summarizePii(piiTypes) {
  return Object.entries(piiTypes || {})
    .map(([type, count]) => `${count} ${type}`)
    .join(', ');
}

function buildDetails(type, { source, piiTypes }) {
  if (type === 'injection') {
    return `Blocked prompt injection${source ? ` (${source})` : ''}`;
  }
  if (type === 'pii_input') {
    return `Blocked input containing PII: ${summarizePii(piiTypes)}`;
  }
  return `Redacted PII from response: ${summarizePii(piiTypes)}`;
}

/** Drop undefined/null values and empty objects so the stored doc stays tidy. */
function compact(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined || v === null) {
      continue;
    }
    if (typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0) {
      continue;
    }
    out[k] = v;
  }
  return out;
}

/**
 * Record a guardrail ENFORCEMENT event into the audit log. Metadata-only: never
 * stores the prompt, the response, or any PII value — only types, counts, and
 * detector provenance. Fire-and-forget and never throws, so guardrail auditing
 * can never break the chat. Disabled with GUARDRAIL_AUDIT_ENABLED=false.
 *
 * @param {Object} params
 * @param {'injection'|'pii_input'|'pii_output'} params.type
 * @param {import('express').Request} params.req
 * @param {string} [params.model]
 * @param {string} [params.source]   - 'ai' | 'heuristic' | 'fallback' (injection)
 * @param {string} [params.language]
 * @param {string} [params.mode]
 * @param {string|null} [params.rule] - matched heuristic rule id (injection)
 * @param {Record<string, number>} [params.piiTypes]
 */
function recordGuardrailEvent({ type, req, model, source, language, mode, rule, piiTypes } = {}) {
  try {
    if (process.env.GUARDRAIL_AUDIT_ENABLED === 'false') {
      return;
    }
    const action = ACTION_BY_TYPE[type];
    if (!action) {
      return;
    }
    const userId = req?.user?.id;
    const entry = {
      action,
      actorName: 'system:guardrail',
      targetType: 'user',
      targetId: userId ? String(userId) : undefined,
      targetName: req?.user?.name || req?.user?.email || undefined,
      details: buildDetails(type, { source, piiTypes }),
      metadata: compact({ model, source, language, mode, rule, piiTypes }),
      status: 'success',
    };
    // Fire-and-forget: do not await (no chat latency); createAuditLog is itself
    // best-effort, and .catch guards against any async rejection.
    Promise.resolve(createAuditLog(entry)).catch(() => {});
  } catch {
    /* best-effort: guardrail auditing must never break chat */
  }
}

module.exports = { recordGuardrailEvent, summarizePii };
