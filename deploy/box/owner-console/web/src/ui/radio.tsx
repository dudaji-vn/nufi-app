import './ui.css';

export function Radio({
  name,
  value,
  checked,
  onChange,
  label,
  hint,
}: {
  name: string;
  value: string;
  checked: boolean;
  onChange: (v: string) => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="ui-radio">
      <input
        type="radio"
        className="ui-radio__input"
        name={name}
        value={value}
        checked={checked}
        onChange={() => onChange(value)}
      />
      <span className="ui-radio__text">
        <span className="ui-radio__label">{label}</span>
        {hint && <span className="ui-radio__hint">{hint}</span>}
      </span>
    </label>
  );
}
