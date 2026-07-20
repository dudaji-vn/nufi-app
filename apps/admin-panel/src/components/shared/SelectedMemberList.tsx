import { X } from 'lucide-react';
import type * as t from '@/types';
import { useLocalize } from '@/hooks';
import { Avatar } from './Avatar';
import { cn } from '@/utils';

export function SelectedMemberList({ users, onRemove, disabled }: t.SelectedMemberListProps) {
  const localize = useLocalize();

  if (users.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-muted-foreground">
        {localize('com_access_no_members')}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="max-h-48 overflow-auto rounded-md border border-border">
        {users.map((user, i) => (
          <div
            key={user.id}
            className={cn(
              'flex items-center justify-between px-3 py-2',
              i < users.length - 1 && 'border-b border-border',
            )}
          >
            <div className="flex items-center gap-3">
              <Avatar name={user.name} size="sm" />
              <div className="flex flex-col">
                <span className="text-sm font-medium text-foreground">{user.name}</span>
                <span className="text-xs text-muted-foreground">{user.email}</span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onRemove(user.id)}
              disabled={disabled}
              aria-label={localize('com_ui_remove_item', { name: user.name })}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:pointer-events-none disabled:opacity-50"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
