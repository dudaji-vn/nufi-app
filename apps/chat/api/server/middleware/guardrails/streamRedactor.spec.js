const { createStreamingRedactor } = require('./streamRedactor');
const { redactOutput } = require('./redact');

/**
 * Simulate the client's append-reconstruction: feed `text` through the redactor
 * in `chunkSize` slices, collecting the cumulative emitted output after every
 * push and after flush. The client concatenates emitted deltas, so `cum` is
 * exactly what the user would see at each step.
 */
function runStream(text, chunkSize = 1) {
  const r = createStreamingRedactor();
  let cum = '';
  const snapshots = [];
  for (let i = 0; i < text.length; i += chunkSize) {
    cum += r.push(text.slice(i, i + chunkSize));
    snapshots.push(cum);
  }
  cum += r.flush();
  snapshots.push(cum);
  return { final: cum, snapshots };
}

const inline = (t) => redactOutput(t, { style: 'inline' }).text;

// Assert no intermediate frame the user sees ever contains a raw secret.
function assertNeverLeaks(snapshots, secrets) {
  for (const snap of snapshots) {
    for (const s of secrets) {
      expect(snap.includes(s)).toBe(false);
    }
  }
}

describe('createStreamingRedactor — never leaks PII mid-stream', () => {
  const cases = [
    { name: 'email (no spaces)', text: 'Contact him at john.doe@example.com anytime.', secrets: ['john.doe@example.com'] },
    { name: 'long email local-part', text: 'Mail: very.long.local.part.over.thirty.chars@corp.co today', secrets: ['very.long.local.part.over.thirty.chars@corp.co'] },
    { name: 'phone no spaces', text: 'Call 415-123-4567 now', secrets: ['415-123-4567'] },
    { name: 'phone with spaces/parens', text: 'Ring (123) 456-7890 please', secrets: ['(123) 456-7890'] },
    { name: 'SSN', text: 'SSN is 123-45-6789 ok', secrets: ['123-45-6789'] },
    { name: 'credit card', text: 'Card 4111 1111 1111 1111 charged', secrets: ['4111 1111 1111 1111'] },
    { name: 'IP address', text: 'Server at 192.168.1.100 responded', secrets: ['192.168.1.100'] },
    { name: 'multiple PII', text: 'a@b.com and 415-123-4567 and 1.2.3.4 end', secrets: ['a@b.com', '415-123-4567', '1.2.3.4'] },
  ];

  for (const c of cases) {
    it(`char-by-char: ${c.name}`, () => {
      const { final, snapshots } = runStream(c.text, 1);
      assertNeverLeaks(snapshots, c.secrets);
      expect(final).toBe(inline(c.text));
    });
    it(`bigger chunks: ${c.name}`, () => {
      const { final, snapshots } = runStream(c.text, 4);
      assertNeverLeaks(snapshots, c.secrets);
      expect(final).toBe(inline(c.text));
    });
  }
});

describe('createStreamingRedactor — preserves & streams normal text', () => {
  it('leaves PII-free text unchanged', () => {
    const text = 'The capital of Vietnam is Hanoi, a lovely city with great food.';
    const { final } = runStream(text, 1);
    expect(final).toBe(text);
  });

  it('streams progressively (emits before flush), not all-at-once', () => {
    const text = 'This is a reasonably long sentence with no sensitive data at all here.';
    const { snapshots } = runStream(text, 1);
    const beforeFlush = snapshots[snapshots.length - 2];
    expect(beforeFlush.length).toBeGreaterThan(0); // something streamed before the final flush
  });

  it('handles empty and whitespace input', () => {
    expect(runStream('', 1).final).toBe('');
    expect(runStream('   ', 1).final).toBe('   ');
  });

  it('final output always equals a single-shot inline redaction', () => {
    const text = 'email x@y.io, phone 0912345678, and normal words in between them all.';
    for (const size of [1, 2, 3, 7, 100]) {
      expect(runStream(text, size).final).toBe(inline(text));
    }
  });

  it('streams a long numeric sequence instead of buffering it all', () => {
    // Regression: an unbounded numeric hold-back used to buffer the ENTIRE
    // response (zero output until flush) for space-separated number runs.
    // Use 2-digit numbers so detectPII's phone rule does not match them.
    const text = Array.from({ length: 60 }, (_, i) => i + 10).join(' ') + ' done';
    const { final, snapshots } = runStream(text, 1);
    expect(final).toBe(text); // PII-free → unchanged
    const beforeFlush = snapshots[snapshots.length - 2];
    // Most of it should have streamed before the final flush (bounded hold-back).
    expect(beforeFlush.length).toBeGreaterThan(text.length / 2);
  });
});

describe('createStreamingRedactor — PII at the very end of the stream', () => {
  const tail = [
    { name: 'email, no trailing char', text: 'his email is john.doe@example.com', secret: 'john.doe@example.com' },
    { name: 'phone with parens, no trailing char', text: 'call (123) 456-7890', secret: '(123) 456-7890' },
    { name: 'credit card, no trailing char', text: 'card 4111 1111 1111 1111', secret: '4111 1111 1111 1111' },
  ];
  for (const c of tail) {
    it(`never leaks and redacts on flush: ${c.name}`, () => {
      const { final, snapshots } = runStream(c.text, 1);
      assertNeverLeaks(snapshots, [c.secret]);
      expect(final).toBe(inline(c.text));
      expect(final.includes(c.secret)).toBe(false);
    });
  }
});
