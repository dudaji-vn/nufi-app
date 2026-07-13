import React from 'react';
import { render, screen } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import Header from '../Header';

const mockUseHasAccess = jest.fn();
const mockUseUIMode = jest.fn();

jest.mock('~/hooks', () => ({
  useHasAccess: (...args: unknown[]) => mockUseHasAccess(...args),
  useUIMode: (...args: unknown[]) => mockUseUIMode(...args),
}));

const mockUseGetStartupConfig = jest.fn();
jest.mock('~/data-provider', () => ({
  useGetStartupConfig: () => mockUseGetStartupConfig(),
}));

jest.mock('../Menus', () => ({
  OpenSidebar: () => <div data-testid="open-sidebar" />,
  PresetsMenu: () => <div data-testid="presets-menu" />,
}));

jest.mock('../Menus/BookmarkMenu', () => ({
  __esModule: true,
  default: () => <div data-testid="bookmark-menu" />,
}));

jest.mock('../AddMultiConvo', () => ({
  __esModule: true,
  default: () => <div data-testid="add-multi-convo" />,
}));

jest.mock('../Menus/Endpoints/ModelSelector', () => ({
  __esModule: true,
  default: () => <div data-testid="model-selector" />,
}));

jest.mock('../ExportAndShareMenu', () => ({
  __esModule: true,
  default: () => <div data-testid="export-and-share-menu" />,
}));

jest.mock('../TemporaryChat', () => ({
  TemporaryChat: () => <div data-testid="temporary-chat" />,
}));

const renderHeader = () =>
  render(
    <RecoilRoot>
      <Header />
    </RecoilRoot>,
  );

describe('Header - UI mode gating', () => {
  beforeEach(() => {
    mockUseHasAccess.mockReturnValue(true);
    mockUseGetStartupConfig.mockReturnValue({
      data: {
        interface: { presets: true, modelSelect: true },
        sharedLinksEnabled: false,
      },
    });
  });

  it('hides Presets, Bookmark, and Multi-convo menus in Basic mode', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'basic',
      isBasic: true,
      isAdvanced: false,
      setMode: jest.fn(),
    });

    renderHeader();

    expect(screen.queryByTestId('presets-menu')).not.toBeInTheDocument();
    expect(screen.queryByTestId('bookmark-menu')).not.toBeInTheDocument();
    expect(screen.queryByTestId('add-multi-convo')).not.toBeInTheDocument();

    // Mode gating only subtracts — unrelated header items still render.
    expect(screen.getByTestId('open-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('model-selector')).toBeInTheDocument();
  });

  it('shows Presets, Bookmark, and Multi-convo menus in Advanced mode when permissions/config allow', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'advanced',
      isBasic: false,
      isAdvanced: true,
      setMode: jest.fn(),
    });

    renderHeader();

    expect(screen.getByTestId('presets-menu')).toBeInTheDocument();
    expect(screen.getByTestId('bookmark-menu')).toBeInTheDocument();
    expect(screen.getByTestId('add-multi-convo')).toBeInTheDocument();
  });

  it('still honors the existing Presets interface gate in Advanced mode', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'advanced',
      isBasic: false,
      isAdvanced: true,
      setMode: jest.fn(),
    });
    mockUseGetStartupConfig.mockReturnValue({
      data: {
        interface: { presets: false, modelSelect: true },
        sharedLinksEnabled: false,
      },
    });

    renderHeader();

    expect(screen.queryByTestId('presets-menu')).not.toBeInTheDocument();
    // Unaffected menus still render in Advanced mode.
    expect(screen.getByTestId('bookmark-menu')).toBeInTheDocument();
    expect(screen.getByTestId('add-multi-convo')).toBeInTheDocument();
  });

  it('still honors the existing permission gates in Advanced mode', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'advanced',
      isBasic: false,
      isAdvanced: true,
      setMode: jest.fn(),
    });
    mockUseHasAccess.mockReturnValue(false);

    renderHeader();

    expect(screen.queryByTestId('bookmark-menu')).not.toBeInTheDocument();
    expect(screen.queryByTestId('add-multi-convo')).not.toBeInTheDocument();
    // Presets is gated by interface config, not useHasAccess — still renders.
    expect(screen.getByTestId('presets-menu')).toBeInTheDocument();
  });
});
