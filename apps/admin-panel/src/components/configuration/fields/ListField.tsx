import { useRef, useLayoutEffect } from 'react';
import type * as t from '@/types';
import {
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui';
import { AddItemButton, TrashButton } from '@/components/shared';
import { useLocalize } from '@/hooks';

export function ListField({
  id,
  values,
  onChange,
  disabled,
  placeholder,
  itemLabel,
  variant = 'inline-edit',
  options,
  'aria-label': ariaLabel,
}: t.ListFieldProps) {
  const localize = useLocalize();
  const listRef = useRef<HTMLDivElement>(null);
  const focusLastRef = useRef(false);

  useLayoutEffect(() => {
    if (focusLastRef.current) {
      focusLastRef.current = false;
      const items = listRef.current?.querySelectorAll<HTMLElement>(
        'input, [role="combobox"]',
      );
      items?.[items.length - 1]?.focus();
    }
  });

  const resolvedPlaceholder = placeholder ?? localize('com_ui_enter_value');
  const resolvedItemLabel = itemLabel ?? localize('com_ui_item');

  const handleAdd = () => {
    if (options) {
      const used = new Set(values);
      const next = options.find((o) => !used.has(o.value))?.value ?? options[0]?.value ?? '';
      onChange([...values, next]);
    } else {
      onChange([...values, '']);
    }
    focusLastRef.current = true;
  };
  const handleRemove = (index: number) => onChange(values.filter((_, i) => i !== index));
  const handleChange = (index: number, val: string) => {
    const next = [...values];
    next[index] = val;
    onChange(next);
  };

  return (
    <div
      ref={listRef}
      id={id}
      className="flex w-full max-w-100 flex-col gap-2"
      role="list"
      aria-label={ariaLabel}
    >
      {values.map((value, index) => {
        const itemAriaLabel = `${resolvedItemLabel} ${index + 1}`;

        let control: React.ReactNode;
        if (options) {
          control = (
            <Select
              value={value || undefined}
              onValueChange={(v) => handleChange(index, v)}
              disabled={disabled}
            >
              <SelectTrigger aria-label={itemAriaLabel} className="flex-1">
                <SelectValue placeholder={resolvedPlaceholder} />
              </SelectTrigger>
              <SelectContent>
                {options.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          );
        } else if (variant === 'inline-edit') {
          control = (
            <Input
              type="text"
              value={value}
              onChange={(e) => handleChange(index, e.target.value)}
              placeholder={resolvedPlaceholder}
              disabled={disabled}
              aria-label={itemAriaLabel}
              className="flex-1"
            />
          );
        } else {
          control = (
            <span className="flex h-10 flex-1 items-center rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground">
              {value}
            </span>
          );
        }

        return (
          <div key={index} className="flex items-center gap-2" role="listitem">
            {control}
            {!disabled && (
              <TrashButton
                onClick={() => handleRemove(index)}
                ariaLabel={`${localize('com_ui_delete')} ${resolvedItemLabel} ${index + 1}`}
              />
            )}
          </div>
        );
      })}

      {!disabled && (!options || values.length < options.length) && (
        <AddItemButton
          label={localize('com_ui_add_item', { item: resolvedItemLabel })}
          onClick={handleAdd}
        />
      )}
    </div>
  );
}
