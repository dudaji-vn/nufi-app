import { formatTimestamp } from '../auditLog/auditLogUtils';
import type { GuardrailAction } from '@/types';

export { formatTimestamp };

/** Guardrail event types surfaced in the Security page filter. */
export const GUARDRAIL_ACTIONS = [
  'guardrail_injection_blocked',
  'guardrail_pii_input_blocked',
  'guardrail_pii_output_redacted',
] as const;

const LABELS: Record<GuardrailAction, string> = {
  guardrail_injection_blocked: 'Injection blocked',
  guardrail_pii_input_blocked: 'PII blocked (input)',
  guardrail_pii_output_redacted: 'PII redacted (output)',
};

export function eventTypeLabel(action: string): string {
  return LABELS[action as GuardrailAction] ?? action;
}

/** Injection = danger; PII = muted (it was safely handled, not an attack). */
export function eventBadgeClass(action: string): string {
  if (action === 'guardrail_injection_blocked') {
    return 'badge-danger';
  }
  return 'bg-muted text-muted-foreground';
}

/** "2 email, 1 phone" from { email: 2, phone: 1 }; "—" when empty. */
export function summarizePiiTypes(piiTypes?: Record<string, number>): string {
  const parts = Object.entries(piiTypes ?? {}).map(
    ([type, count]) => `${count} ${type.toLowerCase()}`,
  );
  return parts.length ? parts.join(', ') : '—';
}
