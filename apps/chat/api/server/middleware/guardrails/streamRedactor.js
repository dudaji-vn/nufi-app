const { detectPII } = require('./detect');
const { redactOutput } = require('./redact');

/**
 * Stateful streaming PII redactor (Tier-2 core algorithm — NOT yet wired into
 * the stream route). Feed it the assistant's text as it streams; it returns
 * only the portion that is safe to show, with any PII masked INLINE, and holds
 * back a small tail until enough has arrived to be sure. Guarantees:
 *
 *   1. No returned output ever contains a raw PII value (mask-before-release).
 *   2. The concatenation of every push() + flush() equals a single-shot inline
 *      redaction of the full text — so the streamed view and the saved message
 *      agree.
 *   3. PII-free text streams progressively (held back only to the last safe
 *      boundary), preserving the live "typing" feel.
 *
 * Strategy: commit up to the last whitespace (never emit the in-progress word),
 * additionally hold a trailing run of number-ish tokens (a space-separated phone
 * or card may still be arriving), and never cut across an already-detected PII
 * match. Emission is prefix-stable, so we only ever append.
 */
const isWs = (ch) => /\s/.test(ch);
const isNumberish = (ch) => /[\d()+\-.]/.test(ch);

/** Pull the commit boundary left over any trailing whitespace-separated run of
 *  number-ish tokens, so a phone/card streamed in space-separated groups is
 *  never partially committed before it is complete. */
function holdTrailingNumberish(raw, start) {
  let i = start;
  for (;;) {
    let j = i;
    while (j > 0 && isWs(raw[j - 1])) {
      j--; // skip whitespace before the token
    }
    let k = j;
    while (k > 0 && isNumberish(raw[k - 1])) {
      k--; // scan the token
    }
    if (k < j && /\d/.test(raw.slice(k, j))) {
      i = k; // token is number-ish (has a digit) → hold it and keep walking left
    } else {
      return i;
    }
  }
}

function safeCommitLength(raw, final) {
  const L = raw.length;
  if (final) {
    return L;
  }
  if (L === 0) {
    return 0;
  }
  // Hold the in-progress word: commit only up to (and including) the last space.
  let b = -1;
  for (let i = L - 1; i >= 0; i--) {
    if (isWs(raw[i])) {
      b = i + 1;
      break;
    }
  }
  if (b < 0) {
    return 0; // still on the very first word — hold everything
  }
  b = holdTrailingNumberish(raw, b);
  // Never cut across a detected PII match (redact it whole, or hold it whole).
  for (const m of detectPII(raw)) {
    const end = m.index + m.value.length;
    if (m.index < b && end > b) {
      b = m.index;
    }
  }
  return Math.max(0, b);
}

function createStreamingRedactor() {
  let raw = '';
  let emitted = ''; // redacted text already returned to the caller

  const step = (final) => {
    const boundary = safeCommitLength(raw, final);
    const redactedCommitted = redactOutput(raw.slice(0, boundary), { style: 'inline' }).text;
    // Emission must be prefix-stable (append-only). If it isn't (should not
    // happen), emit nothing now and let a later step / flush reconcile — this
    // keeps us from ever un-saying or leaking text.
    if (redactedCommitted.length >= emitted.length && redactedCommitted.startsWith(emitted)) {
      const out = redactedCommitted.slice(emitted.length);
      emitted = redactedCommitted;
      return out;
    }
    return '';
  };

  return {
    /** Feed the next streamed text chunk; returns the safe (redacted) text to emit now. */
    push(chunk) {
      raw += chunk == null ? '' : String(chunk);
      return step(false);
    },
    /** Stream ended: commit and return whatever safe text remains. */
    flush() {
      return step(true);
    },
  };
}

module.exports = { createStreamingRedactor, safeCommitLength };
