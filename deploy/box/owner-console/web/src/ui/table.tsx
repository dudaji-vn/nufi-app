import type { ReactNode } from 'react';
import './ui.css';

export type Col<R> = { key: string; label: string; header?: ReactNode; render?: (row: R) => ReactNode };

export function Table<R extends Record<string, unknown>>({
  columns,
  rows,
  empty = 'No data',
  rowKey,
  rowTestId,
}: {
  columns: Col<R>[];
  rows: R[];
  empty?: ReactNode;
  rowKey?: (row: R, index: number) => string | number;
  rowTestId?: (row: R) => string;
}) {
  return (
    <table className="ui-table">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key} scope="col">
              {c.header ?? c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td className="ui-table__empty" colSpan={columns.length}>
              {empty}
            </td>
          </tr>
        ) : (
          rows.map((row, i) => (
            <tr key={rowKey ? rowKey(row, i) : i} data-testid={rowTestId?.(row)}>
              {columns.map((c) => (
                <td key={c.key}>{c.render ? c.render(row) : (row[c.key] as ReactNode)}</td>
              ))}
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
