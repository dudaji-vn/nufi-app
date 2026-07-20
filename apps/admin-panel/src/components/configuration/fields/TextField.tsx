import { useState, useEffect, useRef } from 'react';
import type * as t from '@/types';
import { Input } from '@/components/ui';
import { useLocalize } from '@/hooks';

export function TextField({
  id,
  value,
  onChange,
  placeholder,
  disabled,
  type = 'text',
  ...ariaProps
}: t.TextFieldProps) {
  const localize = useLocalize();
  const [local, setLocal] = useState(value);
  const externalRef = useRef(value);

  useEffect(() => {
    if (value !== externalRef.current) {
      externalRef.current = value;
      setLocal(value);
    }
  }, [value]);

  const commit = () => {
    if (local !== externalRef.current) {
      externalRef.current = local;
      onChange(local);
    }
  };

  return (
    <Input
      id={id}
      type={type}
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit();
      }}
      placeholder={placeholder ?? localize('com_ui_enter_value')}
      disabled={disabled}
      className="max-w-75"
      {...ariaProps}
    />
  );
}
