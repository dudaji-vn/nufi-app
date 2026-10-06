import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import * as api from '../api';
import { General } from './general';

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, 'useControl').mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
});

test('renders four service cards with Running badges', () => {
  vi.spyOn(api, 'useStatus').mockReturnValue({
    isPending: false,
    error: null,
    data: {
      box: { name: 'b' },
      services: ['Web Server', 'Chat', 'Database', 'AI model'].map((name) => ({ name, ok: true, ms: 1 })),
    },
  } as never);
  render(<General />);
  for (const id of ['web-server', 'database', 'chat', 'ai-model']) {
    expect(screen.getByTestId(`service-${id}`).textContent).toContain('Running');
  }
  expect(screen.getByText('Web Server')).toBeTruthy();
});

test('cards show detail when present and none when absent; pill degrades on a down service', () => {
  vi.spyOn(api, 'useStatus').mockReturnValue({
    isPending: false,
    error: null,
    data: {
      box: { name: 'b' },
      services: [
        { name: 'Web Server', ok: true, ms: 1 },
        { name: 'Chat', ok: true, ms: 1, detail: 'v0.1.10' },
        { name: 'Database', ok: false, ms: 1 },
        { name: 'AI model', ok: true, ms: 1, detail: 'qwen3 · 4.5 GB' },
      ],
    },
  } as never);
  render(<General />);
  expect(screen.getByText('qwen3 · 4.5 GB')).toBeTruthy();
  expect(screen.getByTestId('service-chat').textContent).toContain('v0.1.10');
  const db = screen.getByTestId('service-database').textContent ?? '';
  expect(db).toContain('Database');
  expect(db).toContain('Down');
  const web = screen.getByTestId('service-web-server').textContent ?? '';
  expect(web).toContain('Web Server');
  expect(web).toContain('Running');
  expect(screen.getByTestId('status-pill').textContent).toBe('Degraded');
});

test('shows loading and error states', () => {
  const spy = vi.spyOn(api, 'useStatus');
  spy.mockReturnValue({ isPending: true, error: null } as never);
  const { unmount } = render(<General />);
  expect(screen.getByRole('status')).toBeTruthy();
  unmount();
  spy.mockReturnValue({ isPending: false, error: { error: 'unauthorized' } } as never);
  render(<General />);
  expect(screen.getByRole('alert').textContent).toContain('unauthorized');
});
