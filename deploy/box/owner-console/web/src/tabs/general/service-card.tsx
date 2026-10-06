import type { ReactNode } from 'react';

export function ServiceCard({
  id,
  label,
  ok,
  icon,
  subtitle,
}: {
  id: string;
  label: string;
  ok: boolean;
  icon: ReactNode;
  subtitle?: string;
}) {
  return (
    <div className="svc-card" data-testid={`service-${id}`}>
      <span className="svc-card__icon">{icon}</span>
      <div className="svc-card__row">
        <span className="svc-card__title">
          {label}
          <span className={`dot dot--${ok ? 'ok' : 'bad'}`} aria-hidden="true" />
        </span>
        <span className={`svc-card__status svc-card__status--${ok ? 'ok' : 'bad'}`}>{ok ? 'Running' : 'Down'}</span>
      </div>
      {subtitle && <p className="svc-card__detail">{subtitle}</p>}
    </div>
  );
}
