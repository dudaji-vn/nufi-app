import { RefreshCw } from 'lucide-react';
import type * as t from '@/types';
import { Badge, Button } from '@/components/ui';
import { useLocalize } from '@/hooks/useLocalize';
import { cn } from '@/utils';

interface LiteLLMSyncBadgeProps {
  /** Undefined when the endpoint has no sync record yet. */
  status?: t.EndpointSyncStatus;
  endpointName: string;
  onResync: () => void;
  isResyncing: boolean;
  disabled?: boolean;
}

/**
 * Per-endpoint LiteLLM gateway sync indicator: a status badge plus a re-sync
 * action. Rendered only when the gateway feature is enabled. `stopPropagation`
 * keeps clicks from toggling the surrounding card header.
 */
export function LiteLLMSyncBadge({
  status,
  endpointName,
  onResync,
  isResyncing,
  disabled,
}: LiteLLMSyncBadgeProps) {
  const localize = useLocalize();
  const effective = isResyncing ? 'pending' : (status?.status ?? 'none');

  let badge;
  switch (effective) {
    case 'active':
      badge = (
        <Badge variant="outline" className="border-green-500/50 text-green-600 dark:text-green-400">
          {localize('com_litellm_synced')}
        </Badge>
      );
      break;
    case 'pending':
      badge = (
        <Badge variant="outline" className="border-amber-500/50 text-amber-600 dark:text-amber-400">
          {localize('com_litellm_syncing')}
        </Badge>
      );
      break;
    case 'failed':
      badge = (
        <Badge variant="destructive" title={status?.lastError ?? undefined}>
          {localize('com_litellm_sync_failed')}
        </Badge>
      );
      break;
    default:
      badge = <Badge variant="secondary">{localize('com_litellm_not_synced')}</Badge>;
  }

  return (
    <span
      className="flex shrink-0 items-center gap-1.5"
      onClick={(e) => e.stopPropagation()}
      role="status"
    >
      {badge}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        disabled={disabled || isResyncing}
        onClick={(e) => {
          e.stopPropagation();
          onResync();
        }}
        aria-label={localize('com_litellm_resync_aria', { name: endpointName })}
        title={localize('com_litellm_resync')}
      >
        <RefreshCw className={cn('h-3.5 w-3.5', isResyncing && 'animate-spin')} />
      </Button>
    </span>
  );
}
