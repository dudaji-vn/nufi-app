import React from 'react';
import { RecoilRoot } from 'recoil';
import { renderHook, act } from '@testing-library/react';
import type { TAssistantsMap } from 'librechat-data-provider';
import useMentions from '../useMentions';
import useUIMode from '~/hooks/useUIMode';

jest.mock('librechat-data-provider/react-query', () => ({
  useGetModelsQuery: () => ({ data: {}, isLoading: false }),
}));

jest.mock('~/data-provider', () => ({
  useGetPresetsQuery: () => ({ data: [], isLoading: false }),
  useGetStartupConfig: () => ({
    data: {
      interface: { modelSelect: true, presets: true },
      modelSpecs: { list: [] },
    },
    isLoading: false,
  }),
  useListAgentsQuery: () => ({ data: null, isLoading: false }),
  useGetEndpointsQuery: (arg?: { select?: unknown }) =>
    arg && 'select' in arg
      ? { data: ['openAI'] }
      : {
          data: { openAI: { userProvide: false, order: 0 } },
          isLoading: false,
        },
}));

jest.mock('~/hooks/Assistants/useAssistantListMap', () => ({
  __esModule: true,
  default: () => ({}),
}));

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <RecoilRoot>{children}</RecoilRoot>
);

describe('useMentions - Basic/Advanced UI mode gating', () => {
  beforeEach(() => localStorage.clear());

  it('returns no @-mention options in Basic mode (default)', () => {
    const { result } = renderHook(
      () => ({
        mentions: useMentions({
          assistantMap: {} as TAssistantsMap,
          includeAssistants: true,
        }),
        uiMode: useUIMode(),
      }),
      { wrapper },
    );

    expect(result.current.uiMode.isBasic).toBe(true);
    expect(result.current.mentions.options).toHaveLength(0);
  });

  it('returns populated model/agent/preset @-mention options in Advanced mode', () => {
    const { result } = renderHook(
      () => ({
        mentions: useMentions({
          assistantMap: {} as TAssistantsMap,
          includeAssistants: true,
        }),
        uiMode: useUIMode(),
      }),
      { wrapper },
    );

    act(() => result.current.uiMode.setMode('advanced'));

    expect(result.current.uiMode.isAdvanced).toBe(true);
    expect(result.current.mentions.options.length).toBeGreaterThan(0);
    expect(result.current.mentions.options.some((o) => o.type === 'endpoint')).toBe(true);
  });
});
