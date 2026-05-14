import { useState } from 'react';
import { Info, X } from 'lucide-react';
import type * as t from '@/types';
import { getScopeTypeConfig } from '@/constants';
import { useLocalize } from '@/hooks';

export function InfoBanner({
  text,
  dismissible = true,
  variant = 'info',
  scopeSelection,
  onBackToBase,
}: t.InfoBannerProps) {
  const localize = useLocalize();
  const [dismissed, setDismissed] = useState(false);

  const [prevKey, setPrevKey] = useState(`${variant}:${text}`);
  const key = `${variant}:${text}`;
  if (key !== prevKey) {
    setPrevKey(key);
    setDismissed(false);
  }

  if (dismissed) return null;

  if (
    (variant === 'scope-edit' || variant === 'scope-preview') &&
    scopeSelection?.type === 'SCOPE'
  ) {
    const scope = scopeSelection.scope;
    const config = getScopeTypeConfig(scope.principalType);
    const ScopeIcon = config.icon;

    return (
      <div
        className="scope-preview-banner flex items-center gap-2 rounded-md px-3 py-2 text-sm"
        role="status"
        aria-live="polite"
      >
        <ScopeIcon aria-hidden="true" className="h-4 w-4" style={{ color: config.color }} />
        <span className="flex-1 text-foreground">
          {localize('com_scope_editing', {
            type: localize(config.labelKey),
            name: scope.name,
          })}
        </span>
        {onBackToBase && (
          <button
            type="button"
            onClick={onBackToBase}
            className="shrink-0 cursor-pointer rounded-md border border-border bg-transparent px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-accent"
          >
            {localize('com_scope_back_to_base')}
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm"
      role="status"
    >
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
      <span className="flex-1 text-foreground">{text}</span>
      {dismissible && (
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="shrink-0 cursor-pointer rounded-md p-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          aria-label={localize('com_ui_dismiss')}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
