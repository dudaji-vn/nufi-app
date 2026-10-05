import type { ReactNode } from 'react';
import './ui.css';

export type BadgeTone = 'ok' | 'bad' | 'warn' | 'neutral';

export function Badge({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  return <span className={`ui-badge ui-badge--${tone}`}>{children}</span>;
}
