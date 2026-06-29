const { redactOutput } = require('./redact');

const MSG = 'Thông tin nhạy cảm đã được ẩn vì lý do bảo mật.';

describe('redactOutput', () => {
  it('returns text unchanged when there is no PII', () => {
    const r = redactOutput('The capital of France is Paris.', { message: MSG });
    expect(r.redacted).toBe(false);
    expect(r.text).toBe('The capital of France is Paris.');
  });

  it('replaces the whole message when PII is present (default style)', () => {
    const r = redactOutput('His email is john@example.com.', { message: MSG });
    expect(r.redacted).toBe(true);
    expect(r.text).toBe(MSG);
    expect(r.types).toContain('EMAIL');
  });

  it('redacts inline when style="inline", keeping surrounding text', () => {
    const r = redactOutput('Contact john@example.com for details.', {
      message: MSG,
      style: 'inline',
    });
    expect(r.redacted).toBe(true);
    expect(r.text).not.toContain('john@example.com');
    expect(r.text).toContain('Contact');
    expect(r.text).toContain('for details');
  });

  it('handles empty / non-string input', () => {
    expect(redactOutput('', { message: MSG }).redacted).toBe(false);
    expect(redactOutput(undefined, { message: MSG }).text).toBe(undefined);
  });
});
