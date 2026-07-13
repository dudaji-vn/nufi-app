import React from 'react';
import { RecoilRoot } from 'recoil';
import { render, screen } from '@testing-library/react';
import BadgeRow from '../BadgeRow';

type UIMode = 'basic' | 'advanced';

let mockMode: UIMode = 'basic';

jest.mock('~/hooks', () => ({
  useChatBadges: () => [],
  useUIMode: () => ({
    mode: mockMode,
    isBasic: mockMode === 'basic',
    isAdvanced: mockMode === 'advanced',
    setMode: (next: UIMode) => {
      mockMode = next;
    },
  }),
}));

jest.mock('~/Providers', () => ({
  BadgeRowProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

jest.mock('../ToolsDropdown', () => ({
  __esModule: true,
  default: () => <div data-testid="tools-dropdown" />,
}));

jest.mock('../WebSearch', () => ({
  __esModule: true,
  default: () => <div data-testid="web-search" />,
}));

jest.mock('../CodeInterpreter', () => ({
  __esModule: true,
  default: () => <div data-testid="code-interpreter" />,
}));

jest.mock('../FileSearch', () => ({
  __esModule: true,
  default: () => <div data-testid="file-search" />,
}));

jest.mock('../Skills', () => ({
  __esModule: true,
  default: () => <div data-testid="skills" />,
}));

jest.mock('../Artifacts', () => ({
  __esModule: true,
  default: () => <div data-testid="artifacts" />,
}));

jest.mock('../MCPSelect', () => ({
  __esModule: true,
  default: () => <div data-testid="mcp-select" />,
}));

jest.mock('../ToolDialogs', () => ({
  __esModule: true,
  default: () => <div data-testid="tool-dialogs" />,
}));

const noop = () => {};

const renderBadgeRow = () =>
  render(
    <RecoilRoot>
      <BadgeRow showEphemeralBadges onChange={noop} isInChat={false} />
    </RecoilRoot>,
  );

describe('BadgeRow', () => {
  beforeEach(() => {
    mockMode = 'basic';
  });

  it('hides advanced badges but keeps Web Search in Basic mode', () => {
    renderBadgeRow();

    expect(screen.getByTestId('web-search')).toBeInTheDocument();
    expect(screen.queryByTestId('tools-dropdown')).not.toBeInTheDocument();
    expect(screen.queryByTestId('code-interpreter')).not.toBeInTheDocument();
    expect(screen.queryByTestId('file-search')).not.toBeInTheDocument();
    expect(screen.queryByTestId('skills')).not.toBeInTheDocument();
    expect(screen.queryByTestId('artifacts')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mcp-select')).not.toBeInTheDocument();
  });

  it('shows all badges in Advanced mode', () => {
    mockMode = 'advanced';
    renderBadgeRow();

    expect(screen.getByTestId('tools-dropdown')).toBeInTheDocument();
    expect(screen.getByTestId('web-search')).toBeInTheDocument();
    expect(screen.getByTestId('code-interpreter')).toBeInTheDocument();
    expect(screen.getByTestId('file-search')).toBeInTheDocument();
    expect(screen.getByTestId('skills')).toBeInTheDocument();
    expect(screen.getByTestId('artifacts')).toBeInTheDocument();
    expect(screen.getByTestId('mcp-select')).toBeInTheDocument();
  });
});
