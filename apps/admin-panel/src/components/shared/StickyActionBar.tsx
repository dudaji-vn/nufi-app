import type * as t from '@/types';
import { Button } from '@/components/ui';

export function StickyActionBar({
  discardLabel,
  saveLabel,
  onDiscard,
  onSave,
  message,
}: t.StickyActionBarProps) {
  return (
    <div className="flex shrink-0 animate-[slideUp_200ms_ease-out] items-center gap-2 border-t border-border bg-card px-6 py-3">
      {message && (
        <span className="flex-1 text-sm font-medium text-foreground">{message}</span>
      )}
      <div className="ml-auto flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={onDiscard}>
          {discardLabel}
        </Button>
        <Button size="sm" onClick={onSave}>
          {saveLabel}
        </Button>
      </div>
    </div>
  );
}
