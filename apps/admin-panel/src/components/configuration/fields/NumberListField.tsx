import { useRef, useLayoutEffect } from 'react';
import type * as t from '@/types';
import { Input } from '@/components/ui';
import { AddItemButton, TrashButton } from '@/components/shared';
import { useLocalize } from '@/hooks';

export function NumberListField({
  id,
  values,
  onChange,
  disabled,
  placeholder,
  itemLabel,
}: t.NumberListFieldProps) {
  const localize = useLocalize();
  const listRef = useRef<HTMLDivElement>(null);
  const focusLastRef = useRef(false);

  useLayoutEffect(() => {
    if (focusLastRef.current) {
      focusLastRef.current = false;
      const inputs = listRef.current?.querySelectorAll<HTMLElement>('input');
      inputs?.[inputs.length - 1]?.focus();
    }
  });

  const resolvedPlaceholder = placeholder ?? localize('com_ui_enter_number');
  const resolvedItemLabel = itemLabel ?? localize('com_ui_item');

  const handleAdd = () => {
    onChange([...values, 0]);
    focusLastRef.current = true;
  };
  const handleRemove = (index: number) => onChange(values.filter((_, i) => i !== index));
  const handleChange = (index: number, val: number) => {
    const next = [...values];
    next[index] = val;
    onChange(next);
  };

  return (
    <div ref={listRef} id={id} className="flex w-full max-w-75 flex-col gap-2" role="list">
      {values.map((value, index) => (
        <div key={index} className="flex items-center gap-2" role="listitem">
          <Input
            type="number"
            value={value}
            onChange={(e) => handleChange(index, Number(e.target.value))}
            placeholder={resolvedPlaceholder}
            disabled={disabled}
            aria-label={`${resolvedItemLabel} ${index + 1}`}
            className="flex-1 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          />
          {!disabled && (
            <TrashButton
              onClick={() => handleRemove(index)}
              ariaLabel={`${localize('com_ui_delete')} ${resolvedItemLabel} ${index + 1}`}
            />
          )}
        </div>
      ))}

      {!disabled && (
        <AddItemButton
          label={localize('com_ui_add_item', { item: resolvedItemLabel })}
          onClick={handleAdd}
        />
      )}
    </div>
  );
}
