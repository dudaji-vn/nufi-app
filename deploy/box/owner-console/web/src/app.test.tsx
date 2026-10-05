import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import * as api from './api';
import { App } from './app';

test('renders the tab shell with General active', () => {
  vi.spyOn(api, 'useStatus').mockReturnValue({ isPending: true, error: null } as never);
  render(<App />);
  expect(screen.getByRole('tab', { name: 'General' }).getAttribute('aria-selected')).toBe('true');
  expect(screen.getByRole('tab', { name: 'Users' })).toBeTruthy();
  expect(screen.getByRole('tab', { name: 'File Sharing' })).toBeTruthy();
});
