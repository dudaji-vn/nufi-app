import React from 'react';
import { renderHook } from '@testing-library/react';
import type { TUser } from 'librechat-data-provider';
import type { TAuthContext } from '~/common';
import useShowMarketplace from '../useShowMarketplace';

const mockUseHasAccess = jest.fn();
jest.mock('~/hooks', () => {
  const actualReact = jest.requireActual('react');
  return {
    __esModule: true,
    AuthContext: actualReact.createContext(undefined),
    useHasAccess: () => mockUseHasAccess(),
  };
});

const mockUseUIMode = jest.fn();
jest.mock('~/hooks/useUIMode', () => ({
  __esModule: true,
  default: () => mockUseUIMode(),
}));

import { AuthContext } from '~/hooks';

const mockUser: TUser = {
  id: 'user-1',
  username: 'test-user',
  email: 'test-user@example.com',
  name: 'Test User',
  avatar: '',
  role: 'USER',
  provider: 'local',
  createdAt: '',
  updatedAt: '',
};

const authenticatedContext: TAuthContext = {
  user: mockUser,
  token: 'test-token',
  isAuthenticated: true,
  error: undefined,
  login: jest.fn(),
  logout: jest.fn(),
  setError: jest.fn(),
  roles: {},
};

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <AuthContext.Provider value={authenticatedContext}>{children}</AuthContext.Provider>
);

describe('useShowMarketplace - UI mode gating', () => {
  beforeEach(() => {
    mockUseHasAccess.mockReturnValue(true);
  });

  it('returns false in Basic mode even when the underlying permission logic grants access', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'basic',
      isBasic: true,
      isAdvanced: false,
      setMode: jest.fn(),
    });

    const { result } = renderHook(() => useShowMarketplace(), { wrapper });

    expect(result.current).toBe(false);
  });

  it('returns true in Advanced mode when the underlying permission logic grants access', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'advanced',
      isBasic: false,
      isAdvanced: true,
      setMode: jest.fn(),
    });

    const { result } = renderHook(() => useShowMarketplace(), { wrapper });

    expect(result.current).toBe(true);
  });

  it('still returns false in Advanced mode when the underlying permission logic denies access (mode only subtracts)', () => {
    mockUseHasAccess.mockReturnValue(false);
    mockUseUIMode.mockReturnValue({
      mode: 'advanced',
      isBasic: false,
      isAdvanced: true,
      setMode: jest.fn(),
    });

    const { result } = renderHook(() => useShowMarketplace(), { wrapper });

    expect(result.current).toBe(false);
  });
});
