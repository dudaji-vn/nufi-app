import './ui.css';

export type FilterOption = { value: string; label: string };

// A column header that carries a funnel-icon dropdown (Figma). Shared by the
// Users and File Sharing tables.
export function ColFilter({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: FilterOption[];
}) {
  return (
    <span className="col-head">
      {label}
      <span className={`col-filter${value !== 'all' ? ' col-filter--on' : ''}`}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 6h16M7 12h10M10 18h4" />
        </svg>
        <select aria-label={`Filter by ${label}`} value={value} onChange={(e) => onChange(e.target.value)}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </span>
    </span>
  );
}

// A sortable column header with an up/down (⇅) indicator; the active column
// shows its direction.
export function SortHeader({
  label,
  active,
  dir,
  onToggle,
}: {
  label: string;
  active: boolean;
  dir: 'asc' | 'desc';
  onToggle: () => void;
}) {
  return (
    <button type="button" className={`col-sort${active ? ' col-sort--on' : ''}`} onClick={onToggle}>
      {label}
      <span className="col-sort__ico" aria-hidden="true">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M8 9l4-4 4 4" opacity={active && dir === 'desc' ? 0.3 : 1} />
          <path d="M16 15l-4 4-4-4" opacity={active && dir === 'asc' ? 0.3 : 1} />
        </svg>
      </span>
    </button>
  );
}
