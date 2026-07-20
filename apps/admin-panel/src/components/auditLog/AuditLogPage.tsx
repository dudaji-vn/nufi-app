import { Icon } from '@clickhouse/click-ui';
import { useQuery } from '@tanstack/react-query';
import { useState, useMemo, useCallback } from 'react';
import { EmptyState, LoadingState, SearchInput } from '@/components/shared';
import { auditLogQueryOptions, exportAuditLogCsvFn } from '@/server';
import { AUDIT_ACTIONS, actionBadgeClass, formatTimestamp, humanizeAction } from './auditLogUtils';
import { useLocalize } from '@/hooks';
import { cn } from '@/utils';

export function AuditLogPage() {
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

  const { data: entries = [], isLoading } = useQuery(auditLogQueryOptions(filters));

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const { csv } = await exportAuditLogCsvFn({ data: filters });
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [filters]);

  return (
    <div
      role="region"
      aria-label={localize('com_audit_title')}
      className="flex min-h-0 flex-1 flex-col gap-6 overflow-hidden px-6 pt-6"
    >
      <div>
        <h1 className="text-lg font-semibold text-foreground">{localize('com_audit_title')}</h1>
        <p className="text-sm text-muted-foreground">{localize('com_audit_subtitle')}</p>
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
              aria-label={localize('com_audit_col_action')}
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground transition-colors focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
            >
              <option value="all">{localize('com_audit_filter_all')}</option>
              {AUDIT_ACTIONS.map((value) => (
                <option key={value} value={value}>
                  {humanizeAction(value)}
                </option>
              ))}
            </select>

            <div className="flex items-center gap-2">
              <label htmlFor="audit-date-from" className="text-xs text-muted-foreground">
                {localize('com_audit_date_from')}
              </label>
              <input
                id="audit-date-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground transition-colors focus-visible:ring-2 focus-visible:ring-primary focus-visible:outline-none"
              />
            </div>
            <div className="flex items-center gap-2">
              <label htmlFor="audit-date-to" className="text-xs text-muted-foreground">
                {localize('com_audit_date_to')}
              </label>
              <input
                id="audit-date-to"
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
            aria-label={localize('com_audit_title')}
          >
            <table className="w-full text-left text-sm">
              <caption className="sr-only">{localize('com_audit_title')}</caption>
              <thead className="sticky top-0 z-(--z-sticky)">
                <tr className="border-b border-border bg-muted">
                  <th scope="col" className="w-36 px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_audit_col_action')}
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_audit_col_actor')}
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_audit_col_target')}
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_audit_col_details')}
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-medium text-muted-foreground">
                    {localize('com_audit_col_ip')}
                  </th>
                  <th
                    scope="col"
                    className="px-4 py-2.5 font-medium whitespace-nowrap text-muted-foreground"
                  >
                    {localize('com_audit_col_timestamp')}
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
                          actionBadgeClass(entry.action),
                        )}
                      >
                        {humanizeAction(entry.action)}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground">{entry.actorName}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col">
                        <span className="text-foreground">{entry.targetName || '—'}</span>
                        {entry.targetType && (
                          <span className="text-[10px] text-muted-foreground">
                            {entry.targetType}
                            {entry.capability ? ` · ${entry.capability}` : ''}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{entry.details || '—'}</td>
                    <td className="px-4 py-3 text-xs whitespace-nowrap text-muted-foreground">
                      {entry.ipAddress || '—'}
                    </td>
                    <td className="px-4 py-3 text-xs whitespace-nowrap text-muted-foreground">
                      {formatTimestamp(entry.timestamp)}
                    </td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr>
                    <td colSpan={6}>
                      <EmptyState message={localize('com_audit_empty')} />
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-xs text-muted-foreground" aria-live="polite" aria-atomic="true">
          {localize(
            entries.length === 1 ? 'com_audit_entry_count' : 'com_audit_entry_count_plural',
            { count: entries.length },
          )}
        </p>
      </div>
    </div>
  );
}
