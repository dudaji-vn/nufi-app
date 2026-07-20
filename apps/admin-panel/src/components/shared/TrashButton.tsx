import { Trash2 } from 'lucide-react';
import type * as t from '@/types';
import { Button } from '@/components/ui';
import { cn } from '@/utils';

const sizeClass: Record<NonNullable<t.TrashButtonProps['size']>, string> = {
  xs: 'h-7 w-7 [&_svg]:size-3.5',
  sm: 'h-8 w-8 [&_svg]:size-4',
};

export function TrashButton({ onClick, ariaLabel, size = 'sm', disabled }: t.TrashButtonProps) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      onClick={onClick}
      aria-label={ariaLabel}
      disabled={disabled}
      className={cn(
        'text-muted-foreground hover:bg-destructive/10 hover:text-destructive',
        sizeClass[size],
      )}
    >
      <Trash2 />
    </Button>
  );
}
