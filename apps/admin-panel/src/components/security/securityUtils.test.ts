import { describe, it, expect } from 'vitest';
import { eventBadgeClass, eventTypeLabel, summarizePiiTypes } from './securityUtils';

describe('securityUtils', () => {
  it('summarizes pii type counts', () => {
    expect(summarizePiiTypes({ email: 2, phone: 1 })).toBe('2 email, 1 phone');
    expect(summarizePiiTypes({ EMAIL: 2, PHONE: 1 })).toBe('2 email, 1 phone');
    expect(summarizePiiTypes(undefined)).toBe('—');
  });

  it('labels event types', () => {
    expect(eventTypeLabel('guardrail_injection_blocked')).toBe('Injection blocked');
    expect(eventTypeLabel('guardrail_pii_output_redacted')).toBe('PII redacted (output)');
  });

  it('picks a badge tone per event type', () => {
    expect(eventBadgeClass('guardrail_injection_blocked')).toBe('badge-danger');
    expect(eventBadgeClass('guardrail_pii_output_redacted')).toBe('bg-muted text-muted-foreground');
  });
});
