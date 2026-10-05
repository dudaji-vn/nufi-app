import { useEffect, useId, type ReactNode } from 'react';
import './ui.css';

export function Modal({
  open,
  title,
  onClose,
  children,
  actions,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="ui-modal__backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ui-modal" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="ui-modal__head">
          <h2 className="ui-modal__title" id={titleId}>
            {title}
          </h2>
          <button type="button" className="ui-modal__close" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="ui-modal__body">{children}</div>
        {actions && <div className="ui-modal__actions">{actions}</div>}
      </div>
    </div>
  );
}
