import { render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import * as api from '../api';
import { General } from './general';

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
      services: ['Console', 'Chat', 'Gateway'].map((name) => ({ name, ok: true, ms: 1 })),
    },
  } as never);
  render(<General />);
  for (const id of ['web-server', 'database', 'chat', 'ai-model']) {
    expect(screen.getByTestId(`service-${id}`).textContent).toContain('Running');
  }
  expect(screen.getByText('Web Server')).toBeTruthy();
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
