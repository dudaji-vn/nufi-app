import type * as t from '@/types';
import { capabilityLabel, formatTimestamp } from './auditLogUtils';
import { getScopeTypeConfig } from '@/constants';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

export function AuditLogRow({ entry, isLast }: t.AuditLogRowProps) {
  const localize = useLocalize();
  const targetConfig = getScopeTypeConfig(entry.targetPrincipalType);
  const TargetIcon = targetConfig.icon;

  return (
    <tr
      className={cn(
        'bg-card',
        !isLast && 'border-b border-border',
      )}
    >
      <td className="px-4 py-3">
        <span
          className={cn(
            'inline-block rounded-full px-2 py-0.5 text-[10px] font-medium',
            entry.action === 'grant_assigned' ? 'badge-success' : 'badge-danger',
          )}
        >
          {entry.action === 'grant_assigned'
            ? localize('com_audit_action_assigned')
            : localize('com_audit_action_removed')}
        </span>
      </td>
      <td className="px-4 py-3">
        <span className="flex items-center gap-2">
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium',
              targetConfig.badgeClass,
            )}
          >
            <TargetIcon className="h-3 w-3" />
            {localize(targetConfig.labelKey)}
          </span>
          <span className="text-foreground">{entry.targetName}</span>
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-col">
          <span className="text-foreground">
            {capabilityLabel(entry.capability, localize)}
          </span>
          <span className="text-[10px] text-muted-foreground">{entry.capability}</span>
        </div>
      </td>
      <td className="px-4 py-3 font-medium text-foreground">{entry.actorName}</td>
      <td className="px-4 py-3 text-xs whitespace-nowrap text-muted-foreground">
        {formatTimestamp(entry.timestamp)}
      </td>
    </tr>
  );
}
