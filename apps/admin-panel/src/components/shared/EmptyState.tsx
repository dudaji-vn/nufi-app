import type * as t from '@/types';
import { cn } from '@/utils';

export function EmptyState({ message, className }: t.EmptyStateProps) {
  return (
    <div className={cn('px-4 py-8 text-center text-sm text-muted-foreground', className)}>
      {message}
    </div>
  );
}
