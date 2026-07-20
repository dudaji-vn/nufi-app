import React from 'react';
import { RecoilRoot } from 'recoil';
import { renderHook, act } from '@testing-library/react';
import { EModelEndpoint } from 'librechat-data-provider';
import type { TEndpointsConfig, TStartupConfig } from 'librechat-data-provider';
import useEndpoints from '../useEndpoints';
import useUIMode from '~/hooks/useUIMode';

jest.mock('librechat-data-provider/react-query', () => ({
  useGetModelsQuery: () => ({ data: { openAI: ['gpt-4'] } }),
}));

jest.mock('~/data-provider', () => ({
  useGetEndpointsQuery: () => ({ data: ['openAI'] }),
}));

const endpointsConfig: TEndpointsConfig = {
  [EModelEndpoint.openAI]: { userProvide: false, order: 0 },
};

const startupConfig = {
  interface: { modelSelect: true },
  modelSpecs: {
    list: [
      {
        name: 'curated-spec',
        label: 'Curated Spec',
        preset: { endpoint: EModelEndpoint.openAI, model: 'gpt-4' },
      },
    ],
  },
} as unknown as TStartupConfig;

const startupConfigNoSpecs = {
  interface: { modelSelect: true },
} as unknown as TStartupConfig;

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <RecoilRoot>{children}</RecoilRoot>
);

describe('useEndpoints - Basic/Advanced UI mode gating', () => {
  beforeEach(() => localStorage.clear());

  it('hides raw endpoints in Basic mode when modelSpecs are configured, leaving specs untouched', () => {
    const { result } = renderHook(
      () => ({
        endpoints: useEndpoints({ endpointsConfig, startupConfig }),
        uiMode: useUIMode(),
      }),
      { wrapper },
    );

    expect(result.current.uiMode.isBasic).toBe(true);
    expect(result.current.endpoints.mappedEndpoints).toHaveLength(0);
    // modelSpecs assembly lives outside useEndpoints (ModelSelectorContext); verify the
    // curated spec source data used by that assembly is untouched by this hook's input.
    expect(startupConfig.modelSpecs?.list).toHaveLength(1);
  });

  it('shows raw endpoints in Basic mode when NO modelSpecs are configured', () => {
    // Deployments that rely on raw endpoints (no admin-curated modelSpecs) must still
    // expose a model selector in Basic — otherwise the user cannot pick any model.
    const { result } = renderHook(
      () => ({
        endpoints: useEndpoints({ endpointsConfig, startupConfig: startupConfigNoSpecs }),
        uiMode: useUIMode(),
      }),
      { wrapper },
    );

    expect(result.current.uiMode.isBasic).toBe(true);
    expect(result.current.endpoints.mappedEndpoints.length).toBeGreaterThan(0);
    expect(result.current.endpoints.mappedEndpoints[0].value).toBe(EModelEndpoint.openAI);
  });

  it('shows raw endpoints in Advanced mode', () => {
    const { result } = renderHook(
      () => ({
        endpoints: useEndpoints({ endpointsConfig, startupConfig }),
        uiMode: useUIMode(),
      }),
      { wrapper },
    );

    act(() => result.current.uiMode.setMode('advanced'));

    expect(result.current.uiMode.isAdvanced).toBe(true);
    expect(result.current.endpoints.mappedEndpoints.length).toBeGreaterThan(0);
    expect(result.current.endpoints.mappedEndpoints[0].value).toBe(EModelEndpoint.openAI);
  });
});
