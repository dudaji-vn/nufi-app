const applyOutputGuard = require('./outputGuard');
const { agentUsesFileSearch, shouldBufferOutput } = require('./outputGuard');

describe('shouldBufferOutput', () => {
  afterEach(() => {
    delete process.env.GUARDRAIL_ENABLED;
    delete process.env.GUARDRAIL_PII_OUTPUT_MODE;
    delete process.env.GUARDRAIL_BUFFER_OUTPUT;
  });

  it('does NOT buffer by default (typing preserved) even when guardrails are enabled', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    expect(shouldBufferOutput()).toBe(false);
  });

  it('buffers only when explicitly opted in via GUARDRAIL_BUFFER_OUTPUT=true', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    process.env.GUARDRAIL_BUFFER_OUTPUT = 'true';
    expect(shouldBufferOutput()).toBe(true);
  });

  it('does not buffer when the master switch is off', () => {
    process.env.GUARDRAIL_ENABLED = 'false';
    process.env.GUARDRAIL_BUFFER_OUTPUT = 'true';
    expect(shouldBufferOutput()).toBe(false);
  });

  it('does not buffer when output PII mode is off', () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    process.env.GUARDRAIL_PII_OUTPUT_MODE = 'off';
    process.env.GUARDRAIL_BUFFER_OUTPUT = 'true';
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
    delete process.env.GUARDRAIL_REDACT_MESSAGE;
  });

  it('redacts ungrounded PII in a plain-chat response (text + content)', async () => {
    const response = {
      text: 'His email is john@example.com',
      content: [{ type: 'text', text: 'His email is john@example.com' }],
    };
    const out = await applyOutputGuard(response, { usedRag: false });
    expect(out.text).not.toContain('john@example.com');
    expect(out.content[0].text).not.toContain('john@example.com');
  });

  it('SKIPS redaction when the turn used RAG (returns the real email)', async () => {
    const response = {
      text: 'The vendor email is vendor@corp.com',
      content: [{ type: 'text', text: 'The vendor email is vendor@corp.com' }],
    };
    const out = await applyOutputGuard(response, { usedRag: true });
    expect(out.text).toContain('vendor@corp.com');
  });

  it('is a no-op when the master switch is off', async () => {
    process.env.GUARDRAIL_ENABLED = 'false';
    const response = { text: 'email john@example.com' };
    const out = await applyOutputGuard(response, { usedRag: false });
    expect(out.text).toContain('john@example.com');
  });

  it('is a no-op when output mode is off', async () => {
    process.env.GUARDRAIL_PII_OUTPUT_MODE = 'off';
    const response = { text: 'email john@example.com' };
    const out = await applyOutputGuard(response, { usedRag: false });
    expect(out.text).toContain('john@example.com');
  });

  it('still redacts on RAG turns when GUARDRAIL_PII_OUTPUT_SKIP_RAG=false', async () => {
    process.env.GUARDRAIL_PII_OUTPUT_SKIP_RAG = 'false';
    const response = { text: 'email john@example.com' };
    const out = await applyOutputGuard(response, { usedRag: true });
    expect(out.text).not.toContain('john@example.com');
  });

  it('leaves a clean response untouched', async () => {
    const response = { text: 'Paris is the capital of France' };
    const out = await applyOutputGuard(response, { usedRag: false });
    expect(out.text).toBe('Paris is the capital of France');
  });

  it('uses GUARDRAIL_REDACT_MESSAGE when provided (no AI localization call)', async () => {
    process.env.GUARDRAIL_REDACT_MESSAGE = 'CUSTOM-SECURITY-MSG';
    const localize = jest.fn();
    const response = { text: 'ssn 123-45-6789' };
    const out = await applyOutputGuard(response, { usedRag: false, localize });
    expect(out.text).toBe('CUSTOM-SECURITY-MSG');
    expect(localize).not.toHaveBeenCalled(); // explicit message wins, no AI call
  });

  it('localizes the redaction message via ctx.localize when no explicit message is set', async () => {
    const localize = jest.fn().mockResolvedValue('보안 정책으로 표시할 수 없습니다.');
    const response = { text: 'email john@example.com' };
    const out = await applyOutputGuard(response, { usedRag: false, localize });
    expect(localize).toHaveBeenCalledTimes(1);
    expect(out.text).toBe('보안 정책으로 표시할 수 없습니다.');
  });

  it('does NOT call ctx.localize for a clean response (no redaction needed)', async () => {
    const localize = jest.fn();
    const response = { text: 'Paris is the capital of France' };
    await applyOutputGuard(response, { usedRag: false, localize });
    expect(localize).not.toHaveBeenCalled();
  });

  it('invokes ctx.onRedact with piiTypes when it redacts ungrounded PII', async () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    delete process.env.GUARDRAIL_PII_OUTPUT_MODE; // default: redact_ungrounded
    const onRedact = jest.fn();
    const response = { text: 'Reach me at john@example.com' };
    await applyOutputGuard(response, { usedRag: false, onRedact });
    // detectPII (./detect + ./patterns) tags matches with uppercase type keys
    // (EMAIL, SSN, CREDIT_CARD, IP, PHONE) — assert against the real output shape.
    expect(onRedact).toHaveBeenCalledWith({ piiTypes: { EMAIL: 1 } });
  });

  it('does NOT invoke ctx.onRedact when there is no PII to redact', async () => {
    process.env.GUARDRAIL_ENABLED = 'true';
    const onRedact = jest.fn();
    await applyOutputGuard(
      { text: 'The capital of France is Paris.' },
      { usedRag: false, onRedact },
    );
    expect(onRedact).not.toHaveBeenCalled();
  });
});
