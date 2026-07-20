import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LiteLLMSyncBadge } from './LiteLLMSyncBadge';

vi.mock('@/hooks/useLocalize', () => ({
  default: () => (key: string) => key,
  useLocalize: () => (key: string) => key,
}));

const base = { endpointName: 'OpenAI', onResync: vi.fn(), isResyncing: false };

describe('LiteLLMSyncBadge', () => {
  it('shows Synced for an active endpoint', () => {
    render(
      <LiteLLMSyncBadge
        {...base}
        status={{ status: 'active', modelCount: 2, lastError: null, lastSyncedAt: null }}
      />,
    );
    expect(screen.getByText('com_litellm_synced')).toBeInTheDocument();
  });

  it('shows Sync failed with the error surfaced as a title', () => {
    render(
      <LiteLLMSyncBadge
        {...base}
        status={{ status: 'failed', modelCount: 0, lastError: 'boom', lastSyncedAt: null }}
      />,
    );
    expect(screen.getByText('com_litellm_sync_failed')).toHaveAttribute('title', 'boom');
  });

  it('shows Not synced when there is no sync record', () => {
    render(<LiteLLMSyncBadge {...base} />);
    expect(screen.getByText('com_litellm_not_synced')).toBeInTheDocument();
  });

  it('triggers onResync and stops the click from bubbling to the card header', () => {
    const onResync = vi.fn();
    const onParentClick = vi.fn();
    render(
      <div onClick={onParentClick}>
        <LiteLLMSyncBadge {...base} onResync={onResync} />
      </div>,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(onResync).toHaveBeenCalledTimes(1);
    expect(onParentClick).not.toHaveBeenCalled();
  });

  it('shows Syncing and disables the button while re-syncing', () => {
    render(<LiteLLMSyncBadge {...base} isResyncing />);
    expect(screen.getByText('com_litellm_syncing')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
