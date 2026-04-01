import { IconButton } from '@clickhouse/click-ui';
import type * as t from '@/types';

export function TrashButton({ onClick, ariaLabel, size = 'sm', disabled }: t.TrashButtonProps) {
  return (
    <IconButton
      icon="trash"
      size={size}
      onClick={onClick}
      aria-label={ariaLabel}
      disabled={disabled}
    />
  );
}
