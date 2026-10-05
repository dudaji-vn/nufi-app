import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import * as api from '../api';
import type { FileRow } from '../api';
import { useUi } from '../store';
import { Files, formatSize } from './files';
import { Breadcrumb } from './files/breadcrumb';
import { FileTable, filterRows, sortRows } from './files/file-table';

afterEach(cleanup);

const f = (o: Partial<FileRow>): FileRow => ({
  name: 'a.txt', kind: 'file', size: 2048, uploadedAt: '2026-10-01T00:00:00Z', modifiedAt: '2026-10-02T00:00:00Z', access: 'private', ...o,
});
const mutate = vi.fn();

function mockFiles(data: FileRow[]) {
  vi.spyOn(api, 'useFiles').mockReturnValue({ isPending: false, error: null, data } as never);
}

beforeEach(() => {
  vi.restoreAllMocks();
  mutate.mockReset();
  useUi.setState({ filePath: '' });
  vi.spyOn(api, 'useStatus').mockReturnValue({ data: { box: { name: 'b', departments: ['eng', 'ops'] }, services: [] } } as never);
  vi.spyOn(api, 'useUpload').mockReturnValue({ mutate, isPending: false } as never);
});

test('empty state shows the Figma copy', () => {
  mockFiles([]);
  render(<Files />);
  expect(screen.getByText(/your uploaded files will be listed here/i)).toBeTruthy();
});

test('renders a row per file with human size', () => {
  mockFiles([f({}), f({ name: 'b c.pdf', size: 5 * 1024 * 1024 })]);
  render(<Files />);
  expect(screen.getByText('a.txt')).toBeTruthy();
  expect(screen.getByText('2.0 KB')).toBeTruthy();
  expect(screen.getByText('5.0 MB')).toBeTruthy();
});

test('search filters rows by name', () => {
  mockFiles([f({ name: 'alpha.txt' }), f({ name: 'beta.txt' })]);
  render(<Files />);
  fireEvent.change(screen.getByLabelText('Search files'), { target: { value: 'alp' } });
  expect(screen.getByText('alpha.txt')).toBeTruthy();
  expect(screen.queryByText('beta.txt')).toBeNull();
});

test('dropping a file uploads it', () => {
  mockFiles([]);
  render(<Files />);
  const file = new File(['x'], 'x.txt');
  fireEvent.drop(screen.getByTestId('drop-zone'), { dataTransfer: { files: [file] } });
  expect(mutate).toHaveBeenCalledWith(file, expect.anything());
});

test('shows loading and error states', () => {
  const spy = vi.spyOn(api, 'useFiles');
  spy.mockReturnValue({ isPending: true, error: null } as never);
  const { unmount } = render(<Files />);
  expect(screen.getByRole('status')).toBeTruthy();
  unmount();
  spy.mockReturnValue({ isPending: false, error: { error: 'nope' } } as never);
  render(<Files />);
  expect(screen.getByRole('alert').textContent).toContain('nope');
});

test('formatSize', () => {
  expect(formatSize(0)).toBe('0 B');
  expect(formatSize(999)).toBe('999 B');
  expect(formatSize(1536)).toBe('1.5 KB');
});

test('clicking a folder row navigates into it', () => {
  const spy = vi.spyOn(api, 'useFiles').mockReturnValue({ isPending: false, error: null, data: [f({ name: 'docs', kind: 'dir' })] } as never);
  render(<Files />);
  fireEvent.click(screen.getByText('docs'));
  expect(useUi.getState().filePath).toBe('docs');
  expect(spy).toHaveBeenLastCalledWith('eng', 'docs');
  expect(screen.getByRole('navigation', { name: 'Breadcrumb' }).textContent).toBe('Files›docs');
});

test('Download builds an encoded nested URL', () => {
  useUi.setState({ filePath: 'a b/c' });
  mockFiles([f({ name: 'x y.txt' })]);
  let href = '';
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    href = this.getAttribute('href') ?? '';
  });
  render(<Files />);
  fireEvent.click(screen.getByLabelText('Actions for x y.txt'));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Download' }));
  expect(href).toBe('/api/files/eng/a%20b/c/x%20y.txt');
});

test('opening a folder clears the search box', () => {
  mockFiles([f({ name: 'docs', kind: 'dir' })]);
  render(<Files />);
  fireEvent.change(screen.getByLabelText('Search files'), { target: { value: 'doc' } });
  fireEvent.click(screen.getByText('docs'));
  expect((screen.getByLabelText('Search files') as HTMLInputElement).value).toBe('');
});

test('changing department resets the folder', () => {
  useUi.setState({ filePath: 'a/b' });
  mockFiles([]);
  render(<Files />);
  fireEvent.change(screen.getByLabelText('Department'), { target: { value: 'ops' } });
  expect(useUi.getState().filePath).toBe('');
});

test('breadcrumb renders the path and navigates to prefixes', () => {
  const nav = vi.fn();
  render(<Breadcrumb path="a/b" onNavigate={nav} />);
  expect(screen.getByRole('navigation').textContent).toBe('Files›a›b');
  fireEvent.click(screen.getByText('a'));
  expect(nav).toHaveBeenLastCalledWith('a');
  fireEvent.click(screen.getByText('Files'));
  expect(nav).toHaveBeenLastCalledWith('');
  expect(screen.getByText('b').tagName).toBe('SPAN');
});

test('file mutations call the API and invalidate the folder listing', async () => {
  vi.restoreAllMocks();
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
  const qc = new QueryClient();
  const inv = vi.spyOn(qc, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  const { result } = renderHook(
    () => ({
      mkdir: api.useMkdir('eng', 'a'),
      rename: api.useRename('eng', 'a'),
      del: api.useDeleteFile('eng', 'a'),
      access: api.useSetAccess('eng', 'a'),
    }),
    { wrapper },
  );
  const call = async (fn: () => Promise<unknown>, url: string, method: string, body?: unknown) => {
    fetchMock.mockClear();
    inv.mockClear();
    await act(fn);
    await waitFor(() => expect(inv).toHaveBeenCalledWith({ queryKey: ['files', 'eng', 'a'] }));
    const [u, init] = fetchMock.mock.calls[0];
    expect(u).toBe(url);
    expect(init.method).toBe(method);
    if (body) expect(JSON.parse(init.body)).toEqual(body);
  };
  await call(() => result.current.mkdir.mutateAsync('n'), '/api/files/folder', 'POST', { dept: 'eng', path: 'a', name: 'n' });
  await call(() => result.current.rename.mutateAsync({ itemPath: 'a/x', newName: 'y' }), '/api/files/rename', 'POST', { dept: 'eng', path: 'a/x', newName: 'y' });
  await call(() => result.current.del.mutateAsync('a/x y'), '/api/files?dept=eng&path=a%2Fx%20y', 'DELETE');
  await call(() => result.current.access.mutateAsync({ itemPath: 'a/x', access: 'public' }), '/api/files/access', 'PUT', { dept: 'eng', path: 'a/x', access: 'public' });
  vi.unstubAllGlobals();
});

const rowsFixture = [
  f({ name: 'b.txt', size: 10, access: 'public', modifiedAt: '2026-10-03T00:00:00Z' }),
  f({ name: 'a.txt', size: 30, access: 'private', modifiedAt: '2026-10-01T00:00:00Z' }),
  f({ name: 'z', kind: 'dir', size: 0, access: 'private' }),
];
const order = () => screen.getAllByTestId(/^file-row-/).map((r) => r.getAttribute('data-testid')!.slice(9));
const table = (over: Partial<Parameters<typeof FileTable>[0]> = {}) => {
  const onOpen = vi.fn();
  const onAction = vi.fn();
  render(<FileTable rows={rowsFixture} search="" onOpen={onOpen} onAction={onAction} {...over} />);
  return { onOpen, onAction };
};

test('badge shows Private and Public', () => {
  table();
  expect(screen.getByTestId('access-badge-a.txt').textContent).toBe('Private');
  expect(screen.getByTestId('access-badge-b.txt').textContent).toBe('Public');
});

test('sortRows orders by key and keeps folders first', () => {
  expect(sortRows(rowsFixture, 'name', 'asc').map((r) => r.name)).toEqual(['z', 'a.txt', 'b.txt']);
  expect(sortRows(rowsFixture, 'name', 'desc').map((r) => r.name)).toEqual(['z', 'b.txt', 'a.txt']);
  expect(sortRows(rowsFixture, 'size', 'desc').map((r) => r.name)).toEqual(['z', 'a.txt', 'b.txt']);
  expect(sortRows(rowsFixture, 'modifiedAt', 'desc')[1].name).toBe('b.txt');
});

test('filterRows by access and kind', () => {
  expect(filterRows(rowsFixture, { owner: 'all', access: 'public', kind: 'all' }).map((r) => r.name)).toEqual(['b.txt']);
  expect(filterRows(rowsFixture, { owner: 'all', access: 'all', kind: 'dir' }).map((r) => r.name)).toEqual(['z']);
});

test('clicking the Name header toggles sort order', () => {
  table();
  expect(order()).toEqual(['z', 'a.txt', 'b.txt']);
  fireEvent.click(screen.getByRole('button', { name: /^Name/ }));
  expect(order()).toEqual(['z', 'b.txt', 'a.txt']);
});

test('accessibility filter Private hides public rows', () => {
  table();
  fireEvent.change(screen.getByLabelText('Filter by accessibility'), { target: { value: 'private' } });
  expect(screen.queryByTestId('file-row-b.txt')).toBeNull();
  expect(screen.getByTestId('file-row-a.txt')).toBeTruthy();
});

test('context menu lists five items, Create Agent disabled, and fires actions', () => {
  const { onAction } = table();
  fireEvent.click(screen.getByLabelText('Actions for a.txt'));
  const items = screen.getAllByRole('menuitem');
  expect(items.map((i) => i.textContent)).toEqual(['Accessibility', 'Create Agent', 'Rename', 'Download', 'Delete']);
  expect(items[1].getAttribute('aria-disabled')).toBe('true');
  fireEvent.click(items[1]);
  expect(onAction).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }));
  expect(onAction).toHaveBeenLastCalledWith('rename', rowsFixture[1]);
  fireEvent.click(screen.getByLabelText('Actions for a.txt'));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }));
  expect(onAction).toHaveBeenLastCalledWith('delete', rowsFixture[1]);
  fireEvent.click(screen.getByLabelText('Actions for a.txt'));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Accessibility' }));
  expect(onAction).toHaveBeenLastCalledWith('access', rowsFixture[1]);
});

test('a folder row has no Download and its name opens it', () => {
  const { onOpen } = table();
  fireEvent.click(screen.getByLabelText('Actions for z'));
  expect(screen.queryByRole('menuitem', { name: 'Download' })).toBeNull();
  fireEvent.click(screen.getByText('z'));
  expect(onOpen).toHaveBeenCalledWith(rowsFixture[2]);
});
