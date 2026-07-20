import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { QueryKeys, dataService } from 'librechat-data-provider';
import { useAcceptInviteMutation } from '../mutations';

jest.mock('librechat-data-provider', () => {
  const actual = jest.requireActual('librechat-data-provider');
  return {
    ...actual,
    dataService: {
      ...actual.dataService,
      acceptTeamInvite: jest.fn(),
    },
  };
});

const mockAccept = dataService.acceptTeamInvite as jest.Mock;

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { invalidateSpy, wrapper };
}

describe('useAcceptInviteMutation', () => {
  beforeEach(() => mockAccept.mockReset());

  it('invalidates teams, myTeamInvites, and the joined team + members using the returned team id', async () => {
    const teamId = 'team-123';
    mockAccept.mockResolvedValue({ team: { _id: teamId, name: 'T', members: [] } });
    const { invalidateSpy, wrapper } = setup();

    const { result } = renderHook(() => useAcceptInviteMutation(), { wrapper });
    result.current.mutate('tok');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith([QueryKeys.teams]);
    expect(invalidateSpy).toHaveBeenCalledWith([QueryKeys.myTeamInvites]);
    expect(invalidateSpy).toHaveBeenCalledWith([QueryKeys.team, teamId]);
    expect(invalidateSpy).toHaveBeenCalledWith([QueryKeys.teamMembers, teamId]);
  });

  it('does not invalidate a team-scoped key when the response carries no team id', async () => {
    mockAccept.mockResolvedValue({ team: undefined });
    const { invalidateSpy, wrapper } = setup();

    const { result } = renderHook(() => useAcceptInviteMutation(), { wrapper });
    result.current.mutate('tok');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith([QueryKeys.teams]);
    const teamScopedCalls = invalidateSpy.mock.calls.filter(
      (call) => Array.isArray(call[0]) && call[0][0] === QueryKeys.team,
    );
    expect(teamScopedCalls).toHaveLength(0);
  });
});
