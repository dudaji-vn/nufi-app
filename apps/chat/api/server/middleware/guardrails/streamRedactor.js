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
// Upper bound on a single PII match length (email max is 254). Detection scans
// only raw.slice(committed - MAX_MATCH_LEN), so any match that could straddle
// the commit boundary is still seen — this keeps per-push work bounded (O(n)
// total) instead of re-scanning the whole prefix every token (O(n²)).
const MAX_MATCH_LEN = 256;

/** Pull the commit boundary left over a trailing whitespace-separated run of
 *  number-ish tokens (bounded by MAX_PII_HOLD, floored at `floor`), so a
 *  phone/card streamed in space-separated groups is never partially committed
 *  before it is complete. */
function holdTrailingNumberish(raw, start, floor) {
  const limit = Math.max(floor, start - MAX_PII_HOLD);
  let i = start;
  for (;;) {
    let j = i;
    while (j > floor && isWs(raw[j - 1])) {
      j--; // skip whitespace before the token
    }
    let k = j;
    while (k > floor && isNumberish(raw[k - 1])) {
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

/** The raw length that is safe to redact+emit given what is already `committed`. */
function safeCommitLength(raw, committed, final) {
  const L = raw.length;
  if (final) {
    return L;
  }
  if (L <= committed) {
    return committed;
  }
  // Hold the in-progress word: commit only up to the last whitespace in the
  // not-yet-committed tail.
  let b = -1;
  for (let i = L - 1; i >= committed; i--) {
    if (isWs(raw[i])) {
      b = i + 1;
      break;
    }
  }
  if (b < 0) {
    return committed; // no whitespace in the tail yet — hold it
  }
  b = holdTrailingNumberish(raw, b, committed);
  // Never cut across a detected PII match. Scan only a bounded window near the
  // tail so this stays cheap; a match that could straddle `b` starts no earlier
  // than b - MAX_MATCH_LEN ≥ windowStart, so it is always seen.
  const windowStart = Math.max(0, committed - MAX_MATCH_LEN);
  for (const m of detectPII(raw.slice(windowStart))) {
    const start = windowStart + m.index;
    const end = start + m.value.length;
    if (start < b && end > b) {
      b = start;
    }
  }
  return Math.max(committed, b);
}

/**
 * Style/RAG parity (handled by the WIRING, not this module): the streaming
 * redactor always masks INLINE. The route only uses it when
 * GUARDRAIL_PII_OUTPUT_STYLE is 'inline' and the turn is NOT a file_search/RAG
 * turn (see `shouldStreamRedact` in outputGuard.js); the whole-message 'message'
 * style and RAG-skip keep using the existing buffer/passthrough path, so the
 * streamed view and the final saved message always agree.
 */
function createStreamingRedactor() {
  let raw = '';
  let committed = 0; // raw offset already redacted and returned

  const step = (final) => {
    const boundary = safeCommitLength(raw, committed, final);
    if (boundary <= committed) {
      return '';
    }
    // [committed, boundary) never straddles a PII match (word-hold, numeric-hold
    // and the match clamp guarantee it), so it can be redacted independently and
    // the concatenation equals a single-shot inline redaction of the full text.
    const out = redactOutput(raw.slice(committed, boundary), { style: 'inline' }).text;
    committed = boundary;
    return out;
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

/**
 * Transform one streamed SSE event through a redactor. Returns the event to
 * write to the client — with the message-delta text masked inline — or `null`
 * when this delta is held back (write nothing this tick). Any event that is not
 * a message-delta (run steps, tool calls, reasoning, done) passes through
 * unchanged. `messageDeltaType` is the event name that carries assistant text
 * (GraphEvents.ON_MESSAGE_DELTA), passed in so this module stays dependency-free.
 *
 * @param {any} event
 * @param {{ push: (s: string) => string }} redactor
 * @param {string} messageDeltaType
 * @returns {any|null}
 */
function redactStreamEvent(event, redactor, messageDeltaType) {
  if (event && event.event === messageDeltaType) {
    const delta = event.data && event.data.delta;
    const content = delta && delta.content;
    const part = Array.isArray(content) ? content[0] : content;
    if (part && typeof part.text === 'string') {
      const safe = redactor.push(part.text);
      if (!safe) {
        return null; // held back this tick — nothing safe to show yet
      }
      const newPart = { ...part, text: safe };
      const newContent = Array.isArray(content) ? [newPart, ...content.slice(1)] : newPart;
      return { ...event, data: { ...event.data, delta: { ...delta, content: newContent } } };
    }
  }
  return event;
}

module.exports = { createStreamingRedactor, safeCommitLength, redactStreamEvent };
