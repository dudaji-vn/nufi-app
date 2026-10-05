import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import * as api from '../api';
import type { FileRow } from '../api';
import { useUi } from '../store';
import { Files, formatSize } from './files';
import { Breadcrumb } from './files/breadcrumb';

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

test('renders a row per file with human size and a download link', () => {
  mockFiles([f({}), f({ name: 'b c.pdf', size: 5 * 1024 * 1024 })]);
  render(<Files />);
  expect(screen.getByText('a.txt').closest('a')?.getAttribute('href')).toBe('/api/files/eng/a.txt');
  expect(screen.getByText('b c.pdf').closest('a')?.getAttribute('href')).toBe('/api/files/eng/b%20c.pdf');
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

test('file links encode each segment of the nested path', () => {
  useUi.setState({ filePath: 'a b/c' });
  mockFiles([f({ name: 'x y.txt' })]);
  render(<Files />);
  expect(screen.getByText('x y.txt').closest('a')?.getAttribute('href')).toBe('/api/files/eng/a%20b/c/x%20y.txt');
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
