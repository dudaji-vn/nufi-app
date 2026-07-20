import { Icon } from '@clickhouse/click-ui';
import { useState, useCallback } from 'react';
import type * as t from '@/types';
import { useLocalize } from '@/hooks';

const BTN =
  'flex cursor-pointer items-center gap-1 rounded border-none bg-transparent px-1.5 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground';

function dispatchToTopLevelSections(container: HTMLElement, type: string) {
  const roots = container.querySelectorAll('[data-top-level-accordion]');
  for (const root of roots) {
    for (const section of root.querySelectorAll(':scope > section')) {
      section.dispatchEvent(new CustomEvent(type));
    }
  }
}

function expandTopLevelAccordions(container: HTMLElement) {
  dispatchToTopLevelSections(container, 'config:expand');
}

function collapseTopLevelAccordions(container: HTMLElement) {
  dispatchToTopLevelSections(container, 'config:collapse');
}

export function ContentToolbar({
  scrollContainer,
  showConfiguredOnly,
  onShowConfiguredOnlyChange,
  showConfiguredToggle,
}: t.ContentToolbarProps) {
  const localize = useLocalize();
  const [collapsed, setCollapsed] = useState(false);

  const handleExpandAll = useCallback(() => {
    if (!scrollContainer) return;
    expandTopLevelAccordions(scrollContainer);
  }, [scrollContainer]);

  const handleCollapseAll = useCallback(() => {
    if (!scrollContainer) return;
    collapseTopLevelAccordions(scrollContainer);
    scrollContainer.scrollTo({ top: 0, behavior: 'smooth' });
  }, [scrollContainer]);

  return (
    <div className="pointer-events-auto mt-2 mr-3 inline-flex items-center rounded-lg border border-border bg-card/90 shadow-sm backdrop-blur-sm">
      {collapsed ? (
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          title={localize('com_config_show_toolbar')}
          className="flex cursor-pointer items-center border-none bg-transparent px-2.5 py-1.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          <Icon name="gear" size="sm" />
        </button>
      ) : (
        <div className="flex items-center gap-1 px-1.5 py-1">
          <button
            type="button"
            onClick={handleExpandAll}
            title={localize('com_config_expand_all')}
            className={BTN}
          >
            <Icon name="chevron-down" size="xs" />
            <span className="hidden sm:inline">{localize('com_config_expand_all')}</span>
          </button>
          <span className="text-xs text-muted-foreground/60">/</span>
          <button
            type="button"
            onClick={handleCollapseAll}
            title={localize('com_config_collapse_all')}
            className={BTN}
          >
            <Icon name="chevron-right" size="xs" />
            <span className="hidden sm:inline">{localize('com_config_collapse_all')}</span>
          </button>
          {showConfiguredToggle && (
            <>
              <span className="mx-0.5 h-3.5 w-px bg-border" />
              <label
                className="flex cursor-pointer items-center gap-1.5 rounded px-1.5 py-0.5 text-xs text-muted-foreground transition-colors select-none hover:bg-accent has-focus-visible:outline-1 has-focus-visible:outline-ring"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onShowConfiguredOnlyChange(!showConfiguredOnly);
                }}
              >
                <input
                  type="checkbox"
                  checked={showConfiguredOnly}
                  onChange={(e) => onShowConfiguredOnlyChange(e.target.checked)}
                  className="accent-primary focus-visible:outline-none"
                />
                <span className="hidden sm:inline">
                  {localize('com_config_show_configured_only')}
                </span>
              </label>
            </>
          )}
          <span className="mx-0.5 h-3.5 w-px bg-border" />
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            title={localize('com_config_minimize')}
            className={BTN}
          >
            <Icon name="cross" size="xs" />
          </button>
        </div>
      )}
    </div>
  );
}
