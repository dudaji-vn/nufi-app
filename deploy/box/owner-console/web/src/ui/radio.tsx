import './ui.css';

export function Radio({
  name,
  value,
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  name: string;
  value: string;
  checked: boolean;
  onChange: (v: string) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <label className="ui-radio">
      <input
        type="radio"
        className="ui-radio__input"
        name={name}
        value={value}
        checked={checked}
        disabled={disabled}
        onChange={() => onChange(value)}
      />
      <span className="ui-radio__text">
        <span className="ui-radio__label">{label}</span>
        {hint && <span className="ui-radio__hint">{hint}</span>}
      </span>
    </label>
  );
}
