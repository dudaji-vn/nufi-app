jest.mock('~/models', () => ({ createAuditLog: jest.fn() }));
const { createAuditLog } = require('~/models');
const { recordGuardrailEvent } = require('./audit');

const req = { user: { id: 'u1', email: 'user@acme.com', name: 'User' } };

describe('recordGuardrailEvent', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    delete process.env.GUARDRAIL_AUDIT_ENABLED;
  });

  it('writes an injection block entry (metadata-only)', () => {
    recordGuardrailEvent({ type: 'injection', req, model: 'gpt-4o', source: 'heuristic', mode: 'hybrid', rule: 'ignore_prev' });
    expect(createAuditLog).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'guardrail_injection_blocked',
        actorName: 'system:guardrail',
        targetType: 'user',
        targetId: 'u1',
        targetName: 'User',
        status: 'success',
        metadata: { model: 'gpt-4o', source: 'heuristic', mode: 'hybrid', rule: 'ignore_prev' },
      }),
    );
  });

  it('writes a PII output redaction entry with type counts', () => {
    recordGuardrailEvent({ type: 'pii_output', req, model: 'm', piiTypes: { email: 2, phone: 1 } });
    const entry = createAuditLog.mock.calls[0][0];
    expect(entry.action).toBe('guardrail_pii_output_redacted');
    expect(entry.metadata.piiTypes).toEqual({ email: 2, phone: 1 });
    expect(entry.details).toBe('Redacted PII from response: 2 email, 1 phone');
  });

  it('does nothing when GUARDRAIL_AUDIT_ENABLED=false', () => {
    process.env.GUARDRAIL_AUDIT_ENABLED = 'false';
    recordGuardrailEvent({ type: 'injection', req });
    expect(createAuditLog).not.toHaveBeenCalled();
  });

  it('never throws even if createAuditLog throws', () => {
    createAuditLog.mockImplementation(() => {
      throw new Error('db down');
    });
    expect(() => recordGuardrailEvent({ type: 'injection', req })).not.toThrow();
  });

  it('does not throw when called with no arguments', () => {
    expect(() => recordGuardrailEvent()).not.toThrow();
  });

  it('does not throw when req has no user', () => {
    expect(() => recordGuardrailEvent({ type: 'injection', req: {} })).not.toThrow();
  });
});
