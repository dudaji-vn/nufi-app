const { detectPII } = require('./detect');
const { DEFAULT_REDACT_MESSAGE } = require('./patterns');

// Inline marker used when style === 'inline' (keep surrounding text, hide PII).
const INLINE_MARKER = '[đã ẩn vì lý do bảo mật]';

/**
 * Redact PII from model output.
 *
 * Two styles:
 *   - 'message' (default): if any PII is present, the whole text is replaced by
 *     a single natural-language security message (matches the desired UX —
 *     "Tôi không thể hiển thị trực tiếp ... do hạn chế bảo mật").
 *   - 'inline': each PII span is replaced by a short marker, surrounding text kept.
 *
 * Grounding (RAG-skip) is decided by the caller (outputGuard); this function
 * simply redacts whatever PII it finds.
 *
 * @param {string} text
 * @param {{ message?: string, style?: 'message'|'inline' }} [options]
 * @returns {{ text: string, redacted: boolean, types: string[] }}
 */
function redactOutput(text, options = {}) {
  const message = options.message || DEFAULT_REDACT_MESSAGE;
  const style = options.style || 'message';

  if (typeof text !== 'string' || text.length === 0) {
    return { text, redacted: false, types: [] };
  }

  const matches = detectPII(text);
  if (matches.length === 0) {
    return { text, redacted: false, types: [] };
  }

  const types = [...new Set(matches.map((m) => m.type))];

  if (style === 'inline') {
    // Replace from the end so earlier indices stay valid.
    let out = text;
    const ordered = [...matches].sort((a, b) => b.index - a.index);
    for (const m of ordered) {
      out = out.slice(0, m.index) + INLINE_MARKER + out.slice(m.index + m.value.length);
    }
    return { text: out, redacted: true, types };
  }

  return { text: message, redacted: true, types };
}

module.exports = { redactOutput, INLINE_MARKER };
