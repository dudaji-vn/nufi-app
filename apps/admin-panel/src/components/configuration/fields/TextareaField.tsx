import type * as t from '@/types';
import { Textarea } from '@/components/ui';
import { useLocalize } from '@/hooks';

export function TextareaField({
  id,
  value,
  onChange,
  placeholder,
  disabled,
  rows = 3,
  ...ariaProps
}: t.TextareaFieldProps) {
  const localize = useLocalize();

  return (
    <Textarea
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder ?? localize('com_ui_enter_text')}
      disabled={disabled}
      rows={rows}
      className="max-w-75"
      {...ariaProps}
    />
  );
}
