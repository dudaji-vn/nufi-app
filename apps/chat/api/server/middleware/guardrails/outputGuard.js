const { isEnabled } = require('@librechat/api');
const { redactOutput } = require('./redact');

/**
 * Whether an agent uses File Search (RAG) — i.e. the turn's answer may be
 * grounded in the user's own uploaded documents. Used to skip output PII
 * redaction so a manager asking for an email that lives in their document still
 * gets the real email.
 *
 * @param {Object|null|undefined} agent - resolved agent config.
 * @returns {boolean}
 */
function agentUsesFileSearch(agent) {
  if (!agent) {
    return false;
  }
  const tools = Array.isArray(agent.tools) ? agent.tools : [];
  const hasTool = tools.some((tool) =>
    typeof tool === 'string'
      ? tool === 'file_search'
      : tool?.name === 'file_search' || tool?.type === 'file_search',
  );
  const fileIds = agent.tool_resources?.file_search?.file_ids;
  return hasTool || (Array.isArray(fileIds) && fileIds.length > 0);
}

/**
 * Apply the output guardrail to a finished assistant response, in place.
 *
 * Grounded-aware: when the turn used file_search / RAG retrieval, redaction is
 * SKIPPED by default (GUARDRAIL_PII_OUTPUT_SKIP_RAG) so a manager asking for an
 * email that lives in their own uploaded document still gets the real email.
 * On the plain-chat path, ungrounded PII (the model inventing / leaking it) is
 * replaced with a configurable natural-language security message.
 *
 * NOTE on streaming: tokens may already have streamed to the client before this
 * runs; see the design doc for the buffer-then-release / non-stream handling.
 *
 * @param {Object} response - the assistant response (has `.text` and/or `.content`).
 * @param {{ usedRag?: boolean }} [ctx]
 * @returns {Object} the same response object, possibly redacted.
 */
function applyOutputGuard(response, ctx = {}) {
  if (!response || !isEnabled(process.env.GUARDRAIL_ENABLED)) {
    return response;
  }

  const mode = (process.env.GUARDRAIL_PII_OUTPUT_MODE || 'redact_ungrounded').toLowerCase();
  if (mode === 'off') {
    return response;
  }

  const skipRag = process.env.GUARDRAIL_PII_OUTPUT_SKIP_RAG !== 'false';
  if (ctx.usedRag && skipRag) {
    return response; // trust the user's own retrieved documents
  }

  const message = process.env.GUARDRAIL_REDACT_MESSAGE || undefined;
  const style = (process.env.GUARDRAIL_PII_OUTPUT_STYLE || 'message').toLowerCase();

  // Gather every piece of assistant text to decide whether redaction is needed.
  const parts = [];
  if (typeof response.text === 'string') {
    parts.push(response.text);
  }
  if (Array.isArray(response.content)) {
    for (const part of response.content) {
      if (part && part.type === 'text' && typeof part.text === 'string') {
        parts.push(part.text);
      }
    }
  }

  const probe = redactOutput(parts.join('\n'), { message, style });
  if (!probe.redacted) {
    return response;
  }

  if (style === 'inline') {
    if (typeof response.text === 'string') {
      response.text = redactOutput(response.text, { message, style }).text;
    }
    if (Array.isArray(response.content)) {
      response.content = response.content.map((part) =>
        part && part.type === 'text' && typeof part.text === 'string'
          ? { ...part, text: redactOutput(part.text, { message, style }).text }
          : part,
      );
    }
  } else {
    // Whole-message replacement: the entire answer becomes the security message.
    const msg = probe.text;
    if (typeof response.text === 'string' || response.text == null) {
      response.text = msg;
    }
    if (Array.isArray(response.content)) {
      response.content = [{ type: 'text', text: msg }];
    }
  }

  return response;
}

/**
 * Whether the stream subscriber should buffer-then-release the response — i.e.
 * suppress live content chunks and deliver only the final (redacted) message —
 * so a model-leaked PII value never flashes before it is redacted.
 *
 * OFF by default so live "typing" is preserved; opt in with
 * GUARDRAIL_BUFFER_OUTPUT=true when a zero-flash render is preferred over typing.
 *
 * @returns {boolean}
 */
function shouldBufferOutput() {
  return (
    isEnabled(process.env.GUARDRAIL_ENABLED) &&
    (process.env.GUARDRAIL_PII_OUTPUT_MODE || 'redact_ungrounded').toLowerCase() !== 'off' &&
    process.env.GUARDRAIL_BUFFER_OUTPUT === 'true'
  );
}

module.exports = applyOutputGuard;
module.exports.agentUsesFileSearch = agentUsesFileSearch;
module.exports.shouldBufferOutput = shouldBufferOutput;
