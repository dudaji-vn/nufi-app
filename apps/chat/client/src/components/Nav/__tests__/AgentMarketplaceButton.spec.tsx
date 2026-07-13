import React from 'react';
import { render, screen } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import { useNavigate } from 'react-router-dom';
import AgentMarketplaceButton from '../AgentMarketplaceButton';

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: jest.fn(),
}));

jest.mock('@librechat/client', () => ({
  TooltipAnchor: (props: { render: React.ReactNode }) => props.render,
  Button: ({
    children,
    onClick,
    className,
    'data-testid': dataTestId,
    'aria-label': ariaLabel,
  }: React.PropsWithChildren<{
    onClick?: () => void;
    className?: string;
    'data-testid'?: string;
    'aria-label'?: string;
  }>) => (
    <button onClick={onClick} className={className} data-testid={dataTestId} aria-label={ariaLabel}>
      {children}
    </button>
  ),
}));

const mockUseUIMode = jest.fn();
jest.mock('~/hooks/useUIMode', () => ({
  __esModule: true,
  default: () => mockUseUIMode(),
}));

const mockUseShowMarketplace = jest.fn();
jest.mock('~/hooks/Nav/useShowMarketplace', () => ({
  __esModule: true,
  default: () => mockUseShowMarketplace(),
}));

const renderButton = () =>
  render(
    <RecoilRoot>
      <AgentMarketplaceButton toggleNav={() => {}} />
    </RecoilRoot>,
  );

describe('AgentMarketplaceButton - UI mode gating', () => {
  beforeEach(() => {
    (useNavigate as jest.Mock).mockReturnValue(jest.fn());
  });

  it('renders nothing in Basic mode even when marketplace access is granted', () => {
    mockUseShowMarketplace.mockReturnValue(true);
    mockUseUIMode.mockReturnValue({
      mode: 'basic',
      isBasic: true,
      isAdvanced: false,
      setMode: jest.fn(),
    });

    const { container } = renderButton();

    expect(screen.queryByTestId('nav-agents-marketplace-button')).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the marketplace button in Advanced mode when access is granted', () => {
    mockUseShowMarketplace.mockReturnValue(true);
    mockUseUIMode.mockReturnValue({
      mode: 'advanced',
      isBasic: false,
      isAdvanced: true,
      setMode: jest.fn(),
    });

    renderButton();

    expect(screen.getByTestId('nav-agents-marketplace-button')).toBeInTheDocument();
  });

  it('still renders nothing in Advanced mode when marketplace access is not granted (mode only subtracts)', () => {
    mockUseShowMarketplace.mockReturnValue(false);
    mockUseUIMode.mockReturnValue({
      mode: 'advanced',
      isBasic: false,
      isAdvanced: true,
      setMode: jest.fn(),
    });

    renderButton();

    expect(screen.queryByTestId('nav-agents-marketplace-button')).not.toBeInTheDocument();
  });
});
