import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import * as api from '../api';
import type { UserRow } from '../api';
import { Users } from './users';
import { remaining } from './users/user-table';

afterEach(cleanup);

const row = (o: Partial<UserRow>): UserRow => ({
  id: 'u1', name: 'Sun', os: 'macos', keyId: 'k1', token: 'tok/en+1', createdAt: '2026-10-01T00:00:00Z', activation: 'pending', ...o,
});
const mutate = vi.fn();
const idle = { mutate: vi.fn(), isPending: false } as never;

function mockUsers(data: UserRow[]) {
  vi.spyOn(api, 'useUsers').mockReturnValue({ isPending: false, error: null, data } as never);
}

beforeEach(() => {
  vi.restoreAllMocks();
  mutate.mockReset();
  vi.spyOn(api, 'useAddUser').mockReturnValue({ mutate, isPending: false } as never);
  vi.spyOn(api, 'useDeleteUser').mockReturnValue(idle);
  vi.spyOn(api, 'useRegenerate').mockReturnValue(idle);
  vi.spyOn(api, 'useImportUsers').mockReturnValue(idle);
});

test('renders a user row with a Pending badge', () => {
  mockUsers([row({ expiresAt: new Date(Date.now() + 3600_000).toISOString() })]);
  render(<Users />);
  expect(screen.getByTestId('user-row-u1').textContent).toContain('Sun');
  expect(screen.getByTestId('activation-u1').textContent).toBe('Pending');
  expect(screen.getByTestId('countdown-u1').textContent).toMatch(/\d/);
});

test('each activation state shows its label and tone', () => {
  mockUsers([
    row({ id: 'a', name: 'A', activation: 'activated' }),
    row({ id: 'p', name: 'P', activation: 'pending' }),
    row({ id: 'e', name: 'E', activation: 'expired' }),
  ]);
  render(<Users />);
  const cases: [string, string, string][] = [['a', 'Activated', 'ok'], ['p', 'Pending', 'warn'], ['e', 'Expired', 'bad']];
  for (const [id, label, tone] of cases) {
    const el = screen.getByTestId(`activation-${id}`).firstElementChild as HTMLElement;
    expect(el.textContent).toBe(label);
    expect(el.className).toContain(`ui-badge--${tone}`);
  }
});

test('copy button writes the invite link', () => {
  mockUsers([row({})]);
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  render(<Users />);
  fireEvent.click(screen.getByTestId('copy-u1'));
  expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/connect#token=${encodeURIComponent('tok/en+1')}`);
});

test('Add User opens the modal and submits name + os', () => {
  mockUsers([]);
  render(<Users />);
  expect(screen.queryByRole('dialog')).toBeNull();
  fireEvent.click(screen.getByTestId('add-user'));
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Lan' } });
  fireEvent.change(screen.getByLabelText('OS'), { target: { value: 'linux' } });
  fireEvent.click(screen.getByTestId('add-user-submit'));
  expect(mutate).toHaveBeenCalledWith({ name: 'Lan', os: 'linux' }, expect.anything());
});

test('search filters rows by name', () => {
  mockUsers([row({ id: 'a', name: 'Alice' }), row({ id: 'b', name: 'Bob' })]);
  render(<Users />);
  fireEvent.change(screen.getByLabelText('Search users'), { target: { value: 'ali' } });
  expect(screen.getByTestId('user-row-a')).toBeTruthy();
  expect(screen.queryByTestId('user-row-b')).toBeNull();
});

test('selecting a row reveals the Export CSV bar', () => {
  mockUsers([row({})]);
  render(<Users />);
  expect(screen.queryByTestId('export-csv')).toBeNull();
  fireEvent.click(screen.getByLabelText('Select Sun'));
  expect(screen.getByTestId('export-csv')).toBeTruthy();
});

test('paginates client-side', () => {
  mockUsers(Array.from({ length: 12 }, (_, i) => row({ id: `u${i}`, name: `User${i}` })));
  render(<Users />);
  expect(screen.queryByTestId('user-row-u11')).toBeNull();
  fireEvent.click(screen.getByTestId('next-page'));
  expect(screen.getByTestId('user-row-u11')).toBeTruthy();
});

test('remaining() formats time left', () => {
  const now = Date.parse('2026-10-05T00:00:00Z');
  expect(remaining('2026-10-05T00:00:00Z', now)).toBe('Expired');
  expect(remaining('2026-10-05T00:00:45Z', now)).toBe('45s');
  expect(remaining('2026-10-05T00:05:10Z', now)).toBe('5m 10s');
  expect(remaining('2026-10-05T02:03:00Z', now)).toBe('2h 3m');
  expect(remaining('2026-10-07T03:00:00Z', now)).toBe('2d 3h');
});

test('shows loading and error states', () => {
  const spy = vi.spyOn(api, 'useUsers');
  spy.mockReturnValue({ isPending: true, error: null } as never);
  const { unmount } = render(<Users />);
  expect(screen.getByRole('status')).toBeTruthy();
  unmount();
  spy.mockReturnValue({ isPending: false, error: { error: 'unauthorized' } } as never);
  render(<Users />);
  expect(screen.getByRole('alert').textContent).toContain('unauthorized');
});
