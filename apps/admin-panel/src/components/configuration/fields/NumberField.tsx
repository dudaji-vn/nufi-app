import { useState, useEffect, useRef } from 'react';
import type * as t from '@/types';
import { Input } from '@/components/ui';
import { useLocalize } from '@/hooks';

export function NumberField({
  id,
  value,
  onChange,
  placeholder,
  disabled,
  min,
  max,
  step = 1,
  ...ariaProps
}: t.NumberFieldProps) {
  const localize = useLocalize();
  const [local, setLocal] = useState(value != null ? String(value) : '');
  const externalRef = useRef(value);

  useEffect(() => {
    if (value !== externalRef.current) {
      externalRef.current = value;
      setLocal(value != null ? String(value) : '');
    }
  }, [value]);

  const commit = () => {
    const parsed = local === '' ? undefined : Number(local);
    if (parsed !== externalRef.current) {
      externalRef.current = parsed;
      onChange(parsed);
    }
  };

  return (
    <Input
      id={id}
      type="number"
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit();
      }}
      placeholder={placeholder ?? localize('com_ui_enter_number')}
      disabled={disabled}
      min={min}
      max={max}
      step={step}
      className="max-w-75 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      {...ariaProps}
    />
  );
}
