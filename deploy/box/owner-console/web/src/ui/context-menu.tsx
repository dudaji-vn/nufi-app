import { useEffect, useRef, useState, type ReactNode } from 'react';
import './ui.css';

export type ContextMenuItem = {
  label: string;
  icon?: ReactNode;
  danger?: boolean;
  disabled?: boolean;
  onSelect: () => void;
};

export function ContextMenu({ items, children }: { items: ContextMenuItem[]; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown);
    };
  }, [open]);
  return (
    <span className="ui-menu" ref={root}>
      <span className="ui-menu__trigger" onClick={() => setOpen((o) => !o)}>
        {children}
      </span>
      {open && (
        <div className="ui-menu__panel" role="menu">
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              role="menuitem"
              aria-disabled={it.disabled || undefined}
              className={['ui-menu__item', it.danger && 'ui-menu__item--danger', it.disabled && 'ui-menu__item--disabled']
                .filter(Boolean)
                .join(' ')}
              onClick={() => {
                if (it.disabled) return;
                it.onSelect();
                setOpen(false);
              }}
            >
              {it.icon && <span className="ui-menu__icon">{it.icon}</span>}
              {it.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
