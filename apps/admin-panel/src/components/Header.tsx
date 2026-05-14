import { Search } from 'lucide-react';
import type * as t from '@/types';
import { useLocalize } from '@/hooks';

export function Header({ title, onSearchClick, children }: t.HeaderProps) {
  const localize = useLocalize();
  const isMac =
    typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.userAgent);
  const shortcut = isMac ? '⌘K' : 'Ctrl+K';

  return (
    <header className="sticky top-0 z-30 shrink-0 border-b border-border/60 bg-background/70 backdrop-blur supports-backdrop-filter:bg-background/50">
      <div className="flex min-h-14 items-center gap-3 px-4 py-2.5">
        <div className="flex shrink-0 flex-col">
          {title ? (
            <h1 className="text-base font-semibold text-foreground">{title}</h1>
          ) : (
            <div />
          )}
        </div>
        <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
          {children}
          <div id="header-actions-portal" className="contents" />
          {onSearchClick && (
            <button
              type="button"
              onClick={onSearchClick}
              aria-label={localize('com_cmdk_label')}
              className="group flex h-9 min-w-56 shrink-0 cursor-pointer items-center gap-2 rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground transition-colors hover:border-ring/60 hover:bg-muted hover:text-foreground"
            >
              <Search className="h-3.5 w-3.5" />
              <span className="flex-1 text-left">{localize('com_ui_search')}</span>
              <kbd className="pointer-events-none inline-flex h-5 select-none items-center gap-0.5 rounded border border-border bg-background px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
                {shortcut}
              </kbd>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
