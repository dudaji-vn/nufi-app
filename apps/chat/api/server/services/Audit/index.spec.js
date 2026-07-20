const { toAuditLogEntry } = require('./index');

describe('toAuditLogEntry', () => {
  it('passes the metadata object through', () => {
    const entry = toAuditLogEntry({
      _id: 'abc',
      action: 'guardrail_pii_output_redacted',
      actorName: 'system:guardrail',
      status: 'success',
      metadata: { model: 'm', piiTypes: { email: 1 } },
      createdAt: new Date('2026-07-01T00:00:00.000Z'),
    });
    expect(entry.metadata).toEqual({ model: 'm', piiTypes: { email: 1 } });
    expect(entry.action).toBe('guardrail_pii_output_redacted');
  });
});
