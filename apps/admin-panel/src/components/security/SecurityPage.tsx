import { Icon } from '@clickhouse/click-ui';
import { useQuery } from '@tanstack/react-query';
import { useState, useMemo, useCallback } from 'react';
import { EmptyState, LoadingState, SearchInput } from '@/components/shared';
import { securityEventsQueryOptions, exportSecurityEventsCsvFn } from '@/server';
import {
  GUARDRAIL_ACTIONS,
  eventBadgeClass,
  eventTypeLabel,
  formatTimestamp,
  summarizePiiTypes,
} from './securityUtils';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

const SUMMARY = [
  { action: 'guardrail_injection_blocked', key: 'com_security_summary_injection' },
  { action: 'guardrail_pii_input_blocked', key: 'com_security_summary_pii_input' },
  { action: 'guardrail_pii_output_redacted', key: 'com_security_summary_pii_output' },
] as const;

export function SecurityPage() {
  const localize = useLocalize();
  const [search, setSearch] = useState('');
  const [action, setAction] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [exporting, setExporting] = useState(false);

  const filters = useMemo(
    () => ({
      search: search || undefined,
      action: action !== 'all' ? action : undefined,
      from: dateFrom || undefined,
      to: dateTo || undefined,
    }),
    [search, action, dateFrom, dateTo],
  );

  const { data, isLoading } = useQuery(securityEventsQueryOptions(filters));
  const entries = data?.entries ?? [];
  const counts = data?.countsByAction ?? {};

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const { csv } = await exportSecurityEventsCsvFn({ data: filters });
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `security-events-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [filters]);

  return (
    <div
      role="region"
      aria-label={localize('com_security_title')}
      className="flex min-h-0 flex-1 flex-col gap-6 overflow-hidden px-6 pt-6"
    >
      <div>
        <h1 className="text-lg font-semibold text-foreground">{localize('com_security_title')}</h1>
        <p className="text-sm text-muted-foreground">{localize('com_security_subtitle')}</p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {SUMMARY.map(({ action: a, key }) => (
          <div key={a} className="rounded-lg border border-border bg-card px-4 py-3">
            <div className="text-2xl font-semibold text-foreground">{counts[a] ?? 0}</div>
            <div className="text-xs text-muted-foreground">{localize(key)}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-auto">
        <div className="flex items-center justify-between gap-3">
          <div
            className="flex flex-1 flex-wrap items-center gap-3"
            role="group"
            aria-label={localize('com_a11y_filters')}
          >
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder={localize('com_ui_search')}
              className="relative min-w-50 flex-1"
            />
            <select
              aria-label={localize('com_security_col_type')}
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground transition-colors focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
            >
              <option value="all">{localize('com_security_filter_all')}</option>
              {GUARDRAIL_ACTIONS.map((value) => (
                <option key={value} value={value}>
                  {eventTypeLabel(value)}
                </option>
              ))}
            </select>
            <div className="flex items-center gap-2">
              <label htmlFor="sec-date-from" className="text-xs text-muted-foreground">
                {localize('com_audit_date_from')}
              </label>
              <input
                id="sec-date-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground transition-colors focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
              />
            </div>
            <div className="flex items-center gap-2">
              <label htmlFor="sec-date-to" className="text-xs text-muted-foreground">
                {localize('com_audit_date_to')}
              </label>
              <input
                id="sec-date-to"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground transition-colors focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
              />
            </div>
          </div>

          <button
            type="button"
            onClick={handleExport}
            disabled={exporting || entries.length === 0}
            aria-label={localize('com_audit_export_csv')}
            className="flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-transparent px-3 py-1.5 text-sm text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span aria-hidden="true">
              <Icon name="download" size="xs" />
            </span>
            {localize('com_audit_export_csv')}
          </button>
        </div>

        {isLoading ? (
          <LoadingState />
        ) : (
          <div
            className="min-h-0 flex-1 overflow-auto rounded-lg border border-border"
            tabIndex={0}
            role="region"
            aria-label={localize('com_security_title')}
          >
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{localize('com_security_title')}</caption>
              <thead className="sticky top-0 z-(--z-sticky)">
                <tr className="border-b border-border bg-muted">
                  <th scope="col" className="w-44 px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_security_col_type')}
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_security_col_user')}
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_security_col_model')}
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_security_col_source')}
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_security_col_detection')}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2.5 font-medium whitespace-nowrap text-muted-foreground"
                  >
                    {localize('com_security_col_timestamp')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, i) => (
                  <tr
                    key={entry.id}
                    className={cn('bg-card', i !== entries.length - 1 && 'border-b border-border')}
                  >
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'inline-block rounded-full px-2 py-0.5 text-[10px] font-medium',
                          eventBadgeClass(entry.action),
                        )}
                      >
                        {eventTypeLabel(entry.action)}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground">
                      {entry.targetName || '—'}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {entry.metadata?.model || '—'}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {entry.metadata?.source || '—'}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {summarizePiiTypes(entry.metadata?.piiTypes)}
                    </td>
                    <td className="px-4 py-3 text-xs whitespace-nowrap text-muted-foreground">
                      {formatTimestamp(entry.timestamp)}
                    </td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <EmptyState message={localize('com_security_empty')} />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-xs text-muted-foreground" aria-live="polite" aria-atomic="true">
          {localize(
            entries.length === 1 ? 'com_security_entry_count' : 'com_security_entry_count_plural',
            { count: entries.length },
          )}
        </p>
      </div>
    </div>
  );
}
