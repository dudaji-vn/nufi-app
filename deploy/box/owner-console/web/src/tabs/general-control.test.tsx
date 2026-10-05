import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import * as api from '../api';
import { Controls } from './general/controls';
import { Console } from './general/console';

const mutate = vi.fn();
afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  mutate.mockReset();
  vi.spyOn(api, 'useControl').mockReturnValue({ mutate, isPending: false } as never);
});

test('Restart opens the confirm modal; confirming fires the mutation', () => {
  render(<Controls />);
  expect(screen.queryByRole('dialog')).toBeNull();
  fireEvent.click(screen.getByTestId('control-restart'));
  expect(screen.getByRole('dialog').textContent).toContain('1–2 minutes');
  expect(mutate).not.toHaveBeenCalled();
  fireEvent.change(screen.getByTestId('control-service'), { target: { value: 'caddy' } });
  fireEvent.click(screen.getByTestId('confirm-ok'));
  expect(mutate.mock.calls[0][0]).toEqual({ action: 'restart', service: 'caddy' });
  expect(screen.queryByRole('dialog')).toBeNull();
});

test('Cancel does not fire; Start fires without a modal', () => {
  render(<Controls />);
  fireEvent.click(screen.getByTestId('control-stop'));
  fireEvent.click(screen.getByTestId('confirm-cancel'));
  expect(mutate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId('control-start'));
  expect(mutate.mock.calls[0][0]).toEqual({ action: 'start', service: 'librechat' });
});

test('Console chip streams lines into the panel', async () => {
  vi.spyOn(api, 'streamConsole').mockImplementation(async (_c, onLine) => {
    onLine('a');
    onLine('b');
  });
  render(<Console />);
  fireEvent.click(screen.getByTestId('console-chip-logs-librechat'));
  await screen.findByText(/a\s+b/);
  expect(api.streamConsole).toHaveBeenCalledWith('logs librechat', expect.any(Function));
});
