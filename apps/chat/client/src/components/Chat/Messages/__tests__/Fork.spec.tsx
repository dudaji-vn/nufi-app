import React from 'react';
import { render, screen } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import Fork from '../Fork';

const mockUseUIMode = jest.fn();
jest.mock('~/hooks/useUIMode', () => ({
  __esModule: true,
  default: () => mockUseUIMode(),
}));

const mockNavigateToConvo = jest.fn();
jest.mock('~/hooks/Conversations/useNavigateToConvo', () => ({
  __esModule: true,
  default: () => ({ navigateToConvo: mockNavigateToConvo }),
}));

const mockShowToast = jest.fn();
jest.mock('@librechat/client', () => ({
  useToastContext: () => ({ showToast: mockShowToast }),
}));

const mockMutate = jest.fn();
jest.mock('~/data-provider', () => ({
  useForkConvoMutation: jest.fn(() => ({ mutate: mockMutate })),
}));

const renderFork = () =>
  render(
    <RecoilRoot>
      <Fork
        messageId="msg-1"
        conversationId="convo-1"
        forkingSupported={true}
        latestMessageId="msg-1"
        isLast={false}
      />
    </RecoilRoot>,
  );

describe('Fork - UI mode gating', () => {
  it('renders nothing in Basic mode even when forking is supported', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'basic',
      isBasic: true,
      isAdvanced: false,
      setMode: jest.fn(),
    });

    const { container } = renderFork();

    expect(screen.queryByRole('button', { name: 'Open Fork Menu' })).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the fork affordance in Advanced mode when forking is supported', () => {
    mockUseUIMode.mockReturnValue({
      mode: 'advanced',
      isBasic: false,
      isAdvanced: true,
      setMode: jest.fn(),
    });

    renderFork();

    expect(screen.getByRole('button', { name: 'Open Fork Menu' })).toBeInTheDocument();
  });
});
