import type { AuditLogEntry } from './audit';

/** Non-PII structured context recorded with a guardrail event. */
export interface GuardrailMetadata {
  model?: string;
  /** Injection detector provenance: 'ai' | 'heuristic' | 'fallback'. */
  source?: string;
  language?: string;
  mode?: string;
  rule?: string | null;
  /**
   * Per-type counts with UPPERCASE type keys as emitted by the backend
   * detector, e.g. { EMAIL: 2 }. Never contains PII values.
   */
  piiTypes?: Record<string, number>;
}

/** A guardrail enforcement event (an audit entry with guardrail metadata). */
export interface SecurityEvent extends AuditLogEntry {
  metadata?: GuardrailMetadata;
}

export type GuardrailAction =
  | 'guardrail_injection_blocked'
  | 'guardrail_pii_input_blocked'
  | 'guardrail_pii_output_redacted';
