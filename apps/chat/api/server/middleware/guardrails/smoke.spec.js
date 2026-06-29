// Loads the real require chain (including denyRequest's real dependencies) to
// catch boot-time load / circular-dependency failures that the unit tests miss
// because they mock denyRequest.
describe('guardrails barrel loads with the real dependency chain', () => {
  it('exports the guardrail functions', () => {
    const g = require('./index');
    expect(typeof g.inputGuard).toBe('function');
    expect(typeof g.applyOutputGuard).toBe('function');
    expect(typeof g.agentUsesFileSearch).toBe('function');
    expect(typeof g.detectInjection).toBe('function');
    expect(typeof g.detectPII).toBe('function');
    expect(typeof g.redactOutput).toBe('function');
  });
});
