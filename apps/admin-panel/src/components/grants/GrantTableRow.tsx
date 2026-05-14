import type * as t from '@/types';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

export function GrantTableRow({ row, isLast, onClick, onKeyDown, rowRef }: t.GrantTableRowProps) {
  const localize = useLocalize();

  return (
    <tr
      ref={rowRef}
      tabIndex={0}
      role="button"
      aria-label={localize('com_cap_edit_title', { name: row.name })}
      onClick={onClick}
      onKeyDown={onKeyDown}
      className={cn(
        'cursor-pointer bg-card transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-ring',
        !isLast && 'border-b border-border',
      )}
    >
      <td className="px-4 py-3 font-medium text-foreground">{row.name}</td>
      <td className="px-4 py-3 text-muted-foreground">
        {row.grantCount === 0
          ? localize('com_grants_no_capabilities')
          : localize('com_grants_capability_count', { count: row.grantCount })}
      </td>
      <td className="px-4 py-3">
        <span
          className={cn(
            'inline-block rounded-full px-2 py-0.5 text-[10px] font-medium',
            row.isActive ? 'badge-success' : 'badge-danger',
          )}
        >
          {row.isActive ? localize('com_ui_active') : localize('com_ui_paused')}
        </span>
      </td>
    </tr>
  );
}
