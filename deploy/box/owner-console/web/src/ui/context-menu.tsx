import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import './ui.css';

const MENU_WIDTH = 180;

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
  const [pos, setPos] = useState<CSSProperties>({});
  const toggle = () => {
    if (open) return setOpen(false);
    // position:fixed from the trigger rect so no overflow ancestor can clip the panel
    const r = root.current?.getBoundingClientRect();
    if (r) {
      const estHeight = items.length * 36 + 8;
      const up = r.bottom + 4 + estHeight > window.innerHeight && r.top - 4 - estHeight >= 0;
      const alignLeft = r.right - MENU_WIDTH < 0;
      setPos({
        ...(up ? { bottom: window.innerHeight - r.top + 4 } : { top: r.bottom + 4 }),
        ...(alignLeft ? { left: r.left } : { right: window.innerWidth - r.right }),
      });
    }
    setOpen(true);
  };
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
      <span className="ui-menu__trigger" onClick={toggle}>
        {children}
      </span>
      {open && (
        <div className="ui-menu__panel" role="menu" style={{ position: 'fixed', ...pos }}>
          {items.map((it, i) => (
            <button
              key={i}
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
