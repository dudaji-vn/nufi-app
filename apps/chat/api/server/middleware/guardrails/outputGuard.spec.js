const applyOutputGuard = require('./outputGuard');
const { agentUsesFileSearch, shouldBufferOutput } = require('./outputGuard');

describe('shouldBufferOutput', () => {
  afterEach(() => {
    delete process.env.GUARDRAIL_ENABLED;
    delete process.env.GUARDRAIL_PII_OUTPUT_MODE;
    delete process.env.GUARDRAIL_BUFFER_OUTPUT;
  });

  it('buffers when guardrails are enabled and output redaction is active', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    expect(shouldBufferOutput()).toBe(true);
  });

  it('does not buffer when the master switch is off', () => {
    process.env.GUARDRAIL_ENABLED = 'false';
    expect(shouldBufferOutput()).toBe(false);
  });

  it('does not buffer when output PII mode is off', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    process.env.GUARDRAIL_PII_OUTPUT_MODE = 'off';
    expect(shouldBufferOutput()).toBe(false);
  });

  it('can be disabled explicitly via GUARDRAIL_BUFFER_OUTPUT=false', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    process.env.GUARDRAIL_BUFFER_OUTPUT = 'false';
    expect(shouldBufferOutput()).toBe(false);
  });
});

describe('agentUsesFileSearch', () => {
  it('is true when tools include file_search as a string', () => {
    expect(agentUsesFileSearch({ tools: ['web_search', 'file_search'] })).toBe(true);
  });
  it('is true when tools include a file_search tool object', () => {
    expect(agentUsesFileSearch({ tools: [{ type: 'file_search' }] })).toBe(true);
  });
  it('is true when tool_resources.file_search has file_ids', () => {
    expect(agentUsesFileSearch({ tool_resources: { file_search: { file_ids: ['f1'] } } })).toBe(
      true,
    );
  });
  it('is false for a plain agent without file_search', () => {
    expect(agentUsesFileSearch({ tools: ['web_search'] })).toBe(false);
  });
  it('is false for null / undefined', () => {
    expect(agentUsesFileSearch(null)).toBe(false);
    expect(agentUsesFileSearch(undefined)).toBe(false);
  });
});

describe('applyOutputGuard', () => {
  beforeEach(() => {
    process.env.GUARDRAIL_ENABLED = 'true';
    delete process.env.GUARDRAIL_PII_OUTPUT_MODE;
    delete process.env.GUARDRAIL_PII_OUTPUT_SKIP_RAG;
    delete process.env.GUARDRAIL_PII_OUTPUT_STYLE;
  });
  afterEach(() => {
    delete process.env.GUARDRAIL_ENABLED;
    delete process.env.GUARDRAIL_PII_OUTPUT_MODE;
    delete process.env.GUARDRAIL_PII_OUTPUT_SKIP_RAG;
    delete process.env.GUARDRAIL_PII_OUTPUT_STYLE;
  });

  it('redacts ungrounded PII in a plain-chat response (text + content)', () => {
    const response = {
      text: 'His email is john@example.com',
      content: [{ type: 'text', text: 'His email is john@example.com' }],
    };
    const out = applyOutputGuard(response, { usedRag: false });
    expect(out.text).not.toContain('john@example.com');
    expect(out.content[0].text).not.toContain('john@example.com');
  });

  it('SKIPS redaction when the turn used RAG (returns the real email)', () => {
    const response = {
      text: 'The vendor email is vendor@corp.com',
      content: [{ type: 'text', text: 'The vendor email is vendor@corp.com' }],
    };
    const out = applyOutputGuard(response, { usedRag: true });
    expect(out.text).toContain('vendor@corp.com');
  });

  it('is a no-op when the master switch is off', () => {
    process.env.GUARDRAIL_ENABLED = 'false';
    const response = { text: 'email john@example.com' };
    const out = applyOutputGuard(response, { usedRag: false });
    expect(out.text).toContain('john@example.com');
  });

  it('is a no-op when output mode is off', () => {
    process.env.GUARDRAIL_PII_OUTPUT_MODE = 'off';
    const response = { text: 'email john@example.com' };
    const out = applyOutputGuard(response, { usedRag: false });
    expect(out.text).toContain('john@example.com');
  });

  it('still redacts on RAG turns when GUARDRAIL_PII_OUTPUT_SKIP_RAG=false', () => {
    process.env.GUARDRAIL_PII_OUTPUT_SKIP_RAG = 'false';
    const response = { text: 'email john@example.com' };
    const out = applyOutputGuard(response, { usedRag: true });
    expect(out.text).not.toContain('john@example.com');
  });

  it('leaves a clean response untouched', () => {
    const response = { text: 'Paris is the capital of France' };
    const out = applyOutputGuard(response, { usedRag: false });
    expect(out.text).toBe('Paris is the capital of France');
  });

  it('uses GUARDRAIL_REDACT_MESSAGE when provided (whole-message style)', () => {
    process.env.GUARDRAIL_REDACT_MESSAGE = 'CUSTOM-SECURITY-MSG';
    const response = { text: 'ssn 123-45-6789' };
    const out = applyOutputGuard(response, { usedRag: false });
    expect(out.text).toBe('CUSTOM-SECURITY-MSG');
    delete process.env.GUARDRAIL_REDACT_MESSAGE;
  });
});
