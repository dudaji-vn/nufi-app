import { act, cleanup, render, renderHook, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import * as api from './api';
import { App } from './app';
import { useToast } from './ui/toast';

afterEach(cleanup);

test('renders the tab shell with General active', () => {
  vi.spyOn(api, 'useStatus').mockReturnValue({ isPending: true, error: null } as never);
  render(<App />);
  expect(screen.getByRole('tab', { name: 'General' }).getAttribute('aria-selected')).toBe('true');
  expect(screen.getByRole('tab', { name: 'Users' })).toBeTruthy();
  expect(screen.getByRole('tab', { name: 'File Sharing' })).toBeTruthy();
});

test('mounts the Toaster so pushed toasts are visible', () => {
  vi.spyOn(api, 'useStatus').mockReturnValue({ isPending: true, error: null } as never);
  render(<App />);
  const { result } = renderHook(() => useToast());
  act(() => result.current.push('Stop failed: 503', 'bad'));
  expect(screen.getByText('Stop failed: 503')).toBeTruthy();
});
