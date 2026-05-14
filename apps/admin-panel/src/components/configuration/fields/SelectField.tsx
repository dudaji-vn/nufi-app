import type * as t from '@/types';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui';
import { useLocalize } from '@/hooks';

export function SelectField({
  id,
  value,
  options,
  onChange,
  disabled,
  placeholder,
  'aria-label': ariaLabel,
}: t.SelectFieldProps) {
  const localize = useLocalize();

  return (
    <Select value={value || undefined} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger id={id} aria-label={ariaLabel} className="max-w-75">
        <SelectValue placeholder={placeholder || localize('com_ui_select')} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
