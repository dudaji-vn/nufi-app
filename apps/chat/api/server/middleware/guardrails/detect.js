const { INJECTION_PATTERNS, PII_PATTERNS } = require('./patterns');

/**
 * Detect a prompt-injection / jailbreak attempt in a piece of text.
 *
 * @param {string} text - The user text to scan.
 * @returns {{ detected: boolean, rule: string|null }}
 */
function detectInjection(text) {
  if (typeof text !== 'string' || text.length === 0) {
    return { detected: false, rule: null };
  }
  for (const { id, re } of INJECTION_PATTERNS) {
    if (re.test(text)) {
      return { detected: true, rule: id };
    }
  }
  return { detected: false, rule: null };
}

/**
 * Detect PII occurrences in a piece of text. Overlapping matches are resolved
 * by pattern priority (earlier patterns win), so a credit card / SSN / IP is
 * never also reported as a phone number for the same span.
 *
 * @param {string} text - The text to scan.
 * @returns {Array<{ type: string, value: string, index: number }>}
 */
function detectPII(text) {
  if (typeof text !== 'string' || text.length === 0) {
    return [];
  }

  const candidates = [];
  PII_PATTERNS.forEach(({ type, re }, priority) => {
    const rx = new RegExp(re.source, re.flags.includes('g') ? re.flags : `${re.flags}g`);
    let match;
    while ((match = rx.exec(text)) !== null) {
      candidates.push({
        type,
        value: match[0],
        index: match.index,
        end: match.index + match[0].length,
        priority,
      });
      if (match.index === rx.lastIndex) {
        rx.lastIndex++; // guard against zero-length matches
      }
    }
  });

  // Drop overlapping matches, keeping the earliest / highest-priority one.
  candidates.sort((a, b) => a.index - b.index || a.priority - b.priority);
  const result = [];
  let lastEnd = -1;
  for (const c of candidates) {
    if (c.index >= lastEnd) {
      result.push({ type: c.type, value: c.value, index: c.index });
      lastEnd = c.end;
    }
  }
  return result;
}

module.exports = { detectInjection, detectPII };
