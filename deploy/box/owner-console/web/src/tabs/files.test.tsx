import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import * as api from '../api';
import type { FileRow } from '../api';
import { Files, formatSize } from './files';

afterEach(cleanup);

const f = (o: Partial<FileRow>): FileRow => ({
  name: 'a.txt', kind: 'file', size: 2048, uploadedAt: '2026-10-01T00:00:00Z', modifiedAt: '2026-10-02T00:00:00Z', ...o,
});
const mutate = vi.fn();

function mockFiles(data: FileRow[]) {
  vi.spyOn(api, 'useFiles').mockReturnValue({ isPending: false, error: null, data } as never);
}

beforeEach(() => {
  vi.restoreAllMocks();
  mutate.mockReset();
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
