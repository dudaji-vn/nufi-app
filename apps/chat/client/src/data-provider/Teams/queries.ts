/* Teams — query hooks */
import { QueryKeys, dataService } from 'librechat-data-provider';
import { useQuery } from '@tanstack/react-query';
import type { UseQueryOptions, QueryObserverResult } from '@tanstack/react-query';
import type {
  TTeamsListResponse,
  TTeamDetailResponse,
  TTeamMembersListResponse,
  TTeamInvitesListResponse,
  TTeamKnowledgeListResponse,
  TTeamAgentsListResponse,
  TTeamPromptsListResponse,
} from 'librechat-data-provider';

export const useTeamsQuery = (
  config?: UseQueryOptions<TTeamsListResponse>,
): QueryObserverResult<TTeamsListResponse> => {
  return useQuery<TTeamsListResponse>([QueryKeys.teams], () => dataService.getTeams(), {
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
    ...config,
  });
};

export const useTeamQuery = (
  id: string,
  config?: UseQueryOptions<TTeamDetailResponse>,
): QueryObserverResult<TTeamDetailResponse> => {
  return useQuery<TTeamDetailResponse>([QueryKeys.team, id], () => dataService.getTeam(id), {
    enabled: !!id,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
    ...config,
  });
};

export const useTeamMembersQuery = (
  id: string,
  config?: UseQueryOptions<TTeamMembersListResponse>,
): QueryObserverResult<TTeamMembersListResponse> => {
  return useQuery<TTeamMembersListResponse>(
    [QueryKeys.teamMembers, id],
    () => dataService.getTeamMembers(id),
    {
      enabled: !!id,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
      ...config,
    },
  );
};

export const useTeamInvitesQuery = (
  id: string,
  config?: UseQueryOptions<TTeamInvitesListResponse>,
): QueryObserverResult<TTeamInvitesListResponse> => {
  return useQuery<TTeamInvitesListResponse>(
    [QueryKeys.teamInvites, id],
    () => dataService.getTeamInvites(id),
    {
      enabled: !!id,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
      ...config,
    },
  );
};

export const useMyTeamInvitesQuery = (
  config?: UseQueryOptions<TTeamInvitesListResponse>,
): QueryObserverResult<TTeamInvitesListResponse> => {
  return useQuery<TTeamInvitesListResponse>(
    [QueryKeys.myTeamInvites],
    () => dataService.getMyTeamInvites(),
    {
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
      ...config,
    },
  );
};

export const useTeamKnowledgeQuery = (
  id: string,
  config?: UseQueryOptions<TTeamKnowledgeListResponse>,
): QueryObserverResult<TTeamKnowledgeListResponse> => {
  return useQuery<TTeamKnowledgeListResponse>(
    [QueryKeys.teamKnowledge, id],
    () => dataService.getTeamKnowledge(id),
    {
      enabled: !!id,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
      ...config,
    },
  );
};

export const useTeamAgentsQuery = (
  id: string,
  config?: UseQueryOptions<TTeamAgentsListResponse>,
): QueryObserverResult<TTeamAgentsListResponse> => {
  return useQuery<TTeamAgentsListResponse>(
    [QueryKeys.teamAgents, id],
    () => dataService.getTeamAgents(id),
    {
      enabled: !!id,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
      ...config,
    },
  );
};

export const useTeamPromptsQuery = (
  id: string,
  config?: UseQueryOptions<TTeamPromptsListResponse>,
): QueryObserverResult<TTeamPromptsListResponse> => {
  return useQuery<TTeamPromptsListResponse>(
    [QueryKeys.teamPrompts, id],
    () => dataService.getTeamPrompts(id),
    {
      enabled: !!id,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
      ...config,
    },
  );
};
