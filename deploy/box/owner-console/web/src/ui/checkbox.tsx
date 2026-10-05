import './ui.css';

export function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <label className="ui-check">
      <input type="checkbox" className="ui-check__box" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label && <span className="ui-check__label">{label}</span>}
    </label>
  );
}
