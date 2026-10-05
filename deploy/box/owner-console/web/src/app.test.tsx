import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { App } from './app';

test('renders the shell', () => {
  render(<App />);
  expect(screen.getByText('NuFi box · owner')).toBeTruthy();
});
