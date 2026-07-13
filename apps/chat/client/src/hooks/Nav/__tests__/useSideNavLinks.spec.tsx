import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import { EModelEndpoint } from 'librechat-data-provider';
import type { TEndpointsConfig, TInterfaceConfig } from 'librechat-data-provider';
import type { NavLink } from '~/common';
import useUIMode from '~/hooks/useUIMode';
import useSideNavLinks from '../useSideNavLinks';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}));

jest.mock('~/hooks', () => {
  const actualUIMode = jest.requireActual('~/hooks/useUIMode').default;
  return {
    useHasAccess: () => true,
    useMCPServerManager: () => ({ availableMCPServers: [] }),
    useGetAgentsConfig: () => ({ agentsConfig: { capabilities: [] } }),
    useAgentCapabilities: () => ({ skillsEnabled: true }),
    useUIMode: actualUIMode,
  };
});

// These panels are only referenced as object values (never rendered) by the hook, but
// their real modules pull in heavy/unresolvable transitive deps (e.g. react-vtree via
// SkillsAccordion) at import time — stub them out to keep this a pure hook-logic test.
jest.mock('~/components/SidePanel/MCPBuilder/MCPBuilderPanel', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('~/components/SidePanel/Agents/AgentPanelSwitch', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('~/components/SidePanel/Bookmarks/BookmarkPanel', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('~/components/SidePanel/Builder/PanelSwitch', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('~/components/SidePanel/Parameters/Panel', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('~/components/SidePanel/Memories', () => ({ MemoryPanel: () => null }));
jest.mock('~/components/SidePanel/Files/Panel', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('~/components/Prompts', () => ({ PromptsAccordion: () => null }));
jest.mock('~/components/Skills', () => ({ SkillsAccordion: () => null }));

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <RecoilRoot>{children}</RecoilRoot>
);

const endpointsConfig = {
  [EModelEndpoint.agents]: { disableBuilder: false },
} as unknown as TEndpointsConfig;

const interfaceConfig: Partial<TInterfaceConfig> = { parameters: true };

function useTestHarness() {
  const uiMode = useUIMode();
  const links = useSideNavLinks({
    keyProvided: true,
    endpoint: EModelEndpoint.agents,
    endpointType: EModelEndpoint.agents,
    interfaceConfig,
    endpointsConfig,
  });
  return { uiMode, links };
}

const idsOf = (links: NavLink[]) => links.map((link) => link.id);

describe('useSideNavLinks', () => {
  beforeEach(() => localStorage.clear());

  it('hides advanced panels in basic mode (default)', () => {
    const { result } = renderHook(() => useTestHarness(), { wrapper });

    expect(result.current.uiMode.isBasic).toBe(true);
    expect(idsOf(result.current.links)).not.toEqual(
      expect.arrayContaining(['prompts', 'memories', 'bookmarks', 'files']),
    );
  });

  it('shows advanced panels after switching to advanced mode', () => {
    const { result } = renderHook(() => useTestHarness(), { wrapper });

    act(() => {
      result.current.uiMode.setMode('advanced');
    });

    expect(result.current.uiMode.isAdvanced).toBe(true);
    expect(idsOf(result.current.links)).toEqual(expect.arrayContaining(['files']));
  });

  it('always keeps the hide-panel link ungated', () => {
    const { result } = renderHook(
      () =>
        useSideNavLinks({
          keyProvided: true,
          endpoint: EModelEndpoint.agents,
          endpointType: EModelEndpoint.agents,
          interfaceConfig,
          endpointsConfig,
          hidePanel: () => {},
        }),
      { wrapper },
    );

    expect(idsOf(result.current)).toEqual(expect.arrayContaining(['hide-panel']));
  });
});
