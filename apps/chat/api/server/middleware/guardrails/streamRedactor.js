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

// Longest space-containing PII pattern is a 4-group credit card ("4111 1111
// 1111 1111" = 19 chars); phones with spaces are shorter. We hold a trailing
// numeric run only within this many chars of the commit boundary — enough that
// an in-progress spaced phone/card is never partially committed, but bounded so
// a long PII-free numeric response (tables, stats, ID lists) still STREAMS
// instead of buffering to the end. The full-`raw` detected-match clamp below is
// the real backstop; this only governs not-yet-detected partial numeric tails.
const MAX_PII_HOLD = 32;

/** Pull the commit boundary left over a trailing whitespace-separated run of
 *  number-ish tokens (bounded by MAX_PII_HOLD), so a phone/card streamed in
 *  space-separated groups is never partially committed before it is complete. */
function holdTrailingNumberish(raw, start) {
  const limit = Math.max(0, start - MAX_PII_HOLD);
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
    // Hold the token only if it starts within MAX_PII_HOLD of the boundary; a
    // token older than that cannot be part of a PII match reaching the tail, so
    // commit it (keeps numeric-heavy text streaming instead of buffering).
    if (k < j && k >= limit && /\d/.test(raw.slice(k, j))) {
      i = k; // number-ish token within range → hold it and keep walking left
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

/*
 * WIRING NOTES (must be addressed when this is hooked into routes/agents/index.js):
 *  1. PERF: `step()` re-runs detectPII + redactOutput over the whole committed
 *     prefix on every push → O(n²) for a long streamed message. Before wiring,
 *     make it incremental (scan only raw.slice(prevBoundary - MAX_MATCH_LEN,
 *     boundary) and append only the new redacted delta), or the redaction CPU
 *     will block the event loop on long responses.
 *  2. STYLE/RAG PARITY: this hardcodes { style: 'inline' } and knows nothing of
 *     GUARDRAIL_PII_OUTPUT_STYLE or the RAG-skip rule. `applyOutputGuard`
 *     defaults to whole-message 'message' style and SKIPS redaction on
 *     file_search/RAG turns. The wiring MUST pass the configured style through
 *     and bypass this redactor entirely on RAG turns, or the streamed view and
 *     the saved message will disagree (and RAG PII would be masked live but kept
 *     in the transcript — an unfixable mismatch since the client only appends).
 */
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
