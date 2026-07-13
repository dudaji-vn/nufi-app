import { renderHook, act } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import useUIMode from './useUIMode';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <RecoilRoot>{children}</RecoilRoot>
);

describe('useUIMode', () => {
  beforeEach(() => localStorage.clear());

  it('defaults to basic', () => {
    const { result } = renderHook(() => useUIMode(), { wrapper });
    expect(result.current.mode).toBe('basic');
    expect(result.current.isBasic).toBe(true);
    expect(result.current.isAdvanced).toBe(false);
  });

  it('setMode switches to advanced and persists', () => {
    const { result } = renderHook(() => useUIMode(), { wrapper });
    act(() => result.current.setMode('advanced'));
    expect(result.current.isAdvanced).toBe(true);
    expect(localStorage.getItem('uiMode')).toBe(JSON.stringify('advanced'));
  });
});
