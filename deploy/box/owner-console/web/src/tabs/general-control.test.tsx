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

test('Restart opens the confirm modal; confirming fires the whole-box mutation', () => {
  render(<Controls active />);
  expect(screen.queryByRole('dialog')).toBeNull();
  fireEvent.click(screen.getByTestId('control-restart'));
  expect(screen.getByRole('dialog').textContent).toContain('1–2 minutes');
  expect(mutate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId('confirm-ok'));
  expect(mutate.mock.calls[0][0]).toEqual({ action: 'restart', service: '__box__' });
  expect(screen.queryByRole('dialog')).toBeNull();
});

test('Stop confirms with the disconnect copy; Cancel does not fire, confirm does', () => {
  render(<Controls active />);
  fireEvent.click(screen.getByTestId('control-stop'));
  expect(screen.getByRole('dialog').textContent).toContain('disconnect all users and stop all currently running processes');
  fireEvent.click(screen.getByTestId('confirm-cancel'));
  expect(mutate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTestId('control-stop'));
  fireEvent.click(screen.getByTestId('confirm-ok'));
  expect(mutate.mock.calls[0][0]).toEqual({ action: 'stop', service: '__box__' });
});

test('Start fires without a modal (when the box is not already active)', () => {
  render(<Controls active={false} />);
  fireEvent.click(screen.getByTestId('control-start'));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(mutate.mock.calls[0][0]).toEqual({ action: 'start', service: '__box__' });
});

test('Start is disabled while the box is already active', () => {
  render(<Controls active />);
  expect((screen.getByTestId('control-start') as HTMLButtonElement).disabled).toBe(true);
});

test('Status pill reflects active vs degraded', () => {
  const { rerender } = render(<Controls active />);
  expect(screen.getByTestId('status-pill').textContent).toBe('Active');
  rerender(<Controls active={false} />);
  expect(screen.getByTestId('status-pill').textContent).toBe('Degraded');
});

test('typing a command + Enter streams it into the console', async () => {
  vi.spyOn(api, 'streamConsole').mockImplementation(async (_c, onLine) => {
    onLine('line one');
  });
  render(<Console />);
  const input = screen.getByTestId('console-input');
  fireEvent.change(input, { target: { value: 'doctor' } });
  fireEvent.submit(input.closest('form')!);
  await screen.findByText('line one');
  expect(api.streamConsole).toHaveBeenCalledWith('doctor', expect.any(Function));
});

test('a stream error shows an inline error line', async () => {
  vi.spyOn(api, 'streamConsole').mockRejectedValue({ error: 'invalid command' });
  render(<Console />);
  const input = screen.getByTestId('console-input');
  fireEvent.change(input, { target: { value: 'rm -rf' } });
  fireEvent.submit(input.closest('form')!);
  const err = await screen.findByTestId('console-error');
  expect(err.textContent).toContain('invalid command');
});

test('Console chip streams lines into the panel', async () => {
  vi.spyOn(api, 'streamConsole').mockImplementation(async (_c, onLine) => {
    onLine('a');
    onLine('b');
  });
  render(<Console />);
  fireEvent.click(screen.getByTestId('console-chip-logs-librechat'));
  await screen.findByText('b');
  expect(screen.getByText('a')).toBeTruthy();
  expect(api.streamConsole).toHaveBeenCalledWith('logs librechat', expect.any(Function));
});
