import { Loader2 } from 'lucide-react';
import type * as t from '@/types';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

export function LoadingState({ className }: t.LoadingStateProps) {
  const localize = useLocalize();

  return (
    <div
      className={cn('flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground', className)}
    >
      <Loader2 className="h-4 w-4 animate-spin" />
      {localize('com_ui_loading')}
    </div>
  );
}
