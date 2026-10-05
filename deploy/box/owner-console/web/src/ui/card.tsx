import type { ReactNode } from 'react';
import './ui.css';

export function Card({ title, right, children }: { title?: ReactNode; right?: ReactNode; children?: ReactNode }) {
  return (
    <section className="ui-card">
      {(title || right) && (
        <div className="ui-card__head">
          {title ? <h2 className="ui-card__title">{title}</h2> : <span />}
          {right}
        </div>
      )}
      {children}
    </section>
  );
}
