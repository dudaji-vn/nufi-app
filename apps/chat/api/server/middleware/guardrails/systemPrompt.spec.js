const {
  DEFAULT_SECURITY_SYSTEM_PROMPT,
  securitySystemPrompt,
  withSecuritySystemPrompt,
} = require('./systemPrompt');

describe('securitySystemPrompt', () => {
  afterEach(() => {
    delete process.env.GUARDRAIL_ENABLED;
    delete process.env.GUARDRAIL_SYSTEM_PROMPT;
  });

  it('is empty (layer off) when GUARDRAIL_ENABLED is not set', () => {
    expect(securitySystemPrompt()).toBe('');
  });

  it('returns the default preamble when the guard is enabled', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    expect(securitySystemPrompt()).toBe(DEFAULT_SECURITY_SYSTEM_PROMPT);
  });

  it('uses GUARDRAIL_SYSTEM_PROMPT override when provided', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    process.env.GUARDRAIL_SYSTEM_PROMPT = 'Custom policy.';
    expect(securitySystemPrompt()).toBe('Custom policy.');
  });

  it('is disabled when GUARDRAIL_SYSTEM_PROMPT is an empty string (opt-out)', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    process.env.GUARDRAIL_SYSTEM_PROMPT = '';
    expect(securitySystemPrompt()).toBe('');
  });
});

describe('withSecuritySystemPrompt', () => {
  afterEach(() => {
    delete process.env.GUARDRAIL_ENABLED;
    delete process.env.GUARDRAIL_SYSTEM_PROMPT;
  });

  it('is a pass-through (old behavior) when the guard is off', () => {
    expect(withSecuritySystemPrompt('  Base instructions  ')).toBe('Base instructions');
    expect(withSecuritySystemPrompt('')).toBeUndefined();
    expect(withSecuritySystemPrompt(undefined)).toBeUndefined();
    expect(withSecuritySystemPrompt(null)).toBeUndefined();
  });

  it('prepends the preamble to existing instructions when enabled', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    const out = withSecuritySystemPrompt('Base instructions');
    expect(out.startsWith(DEFAULT_SECURITY_SYSTEM_PROMPT)).toBe(true);
    expect(out).toContain('Base instructions');
  });

  it('returns just the preamble when there are no instructions', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    expect(withSecuritySystemPrompt(undefined)).toBe(DEFAULT_SECURITY_SYSTEM_PROMPT);
  });

  it('is idempotent — never prepends the same preamble twice', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    const once = withSecuritySystemPrompt('Base');
    const twice = withSecuritySystemPrompt(once);
    expect(twice).toBe(once);
  });
});
