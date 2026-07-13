import { render, screen } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import Settings from '../Settings';

const mockUseUIMode = jest.fn();
jest.mock('~/hooks/useUIMode', () => ({
  __esModule: true,
  default: () => mockUseUIMode(),
}));

const mockUsePersonalizationAccess = jest.fn();
jest.mock('~/hooks/usePersonalizationAccess', () => ({
  __esModule: true,
  default: () => mockUsePersonalizationAccess(),
}));

const mockUseGetStartupConfig = jest.fn();
jest.mock('~/data-provider', () => ({
  useGetStartupConfig: () => mockUseGetStartupConfig(),
}));

jest.mock('../SettingsTabs', () => ({
  General: () => <div data-testid="general-tab-content" />,
  Chat: () => <div data-testid="chat-tab-content" />,
  Commands: () => <div data-testid="commands-tab-content" />,
  Speech: () => <div data-testid="speech-tab-content" />,
  Personalization: () => <div data-testid="personalization-tab-content" />,
  Data: () => <div data-testid="data-tab-content" />,
  Balance: () => <div data-testid="balance-tab-content" />,
  Account: () => <div data-testid="account-tab-content" />,
}));

const renderSettings = () =>
  render(
    <RecoilRoot>
      <Settings open onOpenChange={() => {}} />
    </RecoilRoot>,
  );

describe('Settings - UI mode gating', () => {
  beforeEach(() => {
    mockUsePersonalizationAccess.mockReturnValue({
      hasAnyPersonalizationFeature: false,
      hasMemoryOptOut: false,
    });
    mockUseGetStartupConfig.mockReturnValue({ data: { balance: { enabled: false } } });
  });

  it('hides the Chat and Commands tab triggers in Basic mode', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'basic',
      isBasic: true,
      isAdvanced: false,
      setMode: jest.fn(),
    });

    renderSettings();

    expect(screen.queryByText('Chat')).not.toBeInTheDocument();
    expect(screen.queryByText('Commands')).not.toBeInTheDocument();

    // Mode gating only subtracts — unrelated tabs still render.
    expect(screen.getByText('General')).toBeInTheDocument();
    expect(screen.getByText('Speech')).toBeInTheDocument();
    expect(screen.getByText('Data controls')).toBeInTheDocument();
    expect(screen.getByText('Account')).toBeInTheDocument();
  });

  it('shows the Chat and Commands tab triggers in Advanced mode', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'advanced',
      isBasic: false,
      isAdvanced: true,
      setMode: jest.fn(),
    });

    renderSettings();

    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('Commands')).toBeInTheDocument();
    expect(screen.getByText('General')).toBeInTheDocument();
    expect(screen.getByText('Speech')).toBeInTheDocument();
  });
});
