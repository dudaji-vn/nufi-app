/* Teams — mutation hooks */
import { QueryKeys, MutationKeys, dataService } from 'librechat-data-provider';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { UseMutationOptions } from '@tanstack/react-query';
import type {
  TTeam,
  TTeamInvite,
  TCreateTeamRequest,
  TUpdateTeamRequest,
  TCreateInviteRequest,
  TChangeMemberRoleRequest,
  TTransferOwnershipRequest,
  TAddKnowledgeRequest,
  TShareAgentRequest,
  TSharePromptRequest,
  TRemoveMemberRequest,
  TRevokeInviteRequest,
  TRemoveKnowledgeRequest,
  TUnshareAgentRequest,
  TUnsharePromptRequest,
  TSubgroup,
  TCreateSubgroupRequest,
  TUpdateSubgroupRequest,
} from 'librechat-data-provider';

export const useCreateTeamMutation = (
  options?: UseMutationOptions<{ team: TTeam }, Error, TCreateTeamRequest>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ team: TTeam }, Error, TCreateTeamRequest>(
    [MutationKeys.createTeam],
    (data: TCreateTeamRequest) => dataService.createTeam(data),
    {
      ...options,
      onSuccess: (...params) => {
        queryClient.invalidateQueries([QueryKeys.teams]);
        options?.onSuccess?.(...params);
      },
    },
  );
};

export const useUpdateTeamMutation = (
  options?: UseMutationOptions<{ team: TTeam }, Error, TUpdateTeamRequest & { teamId: string }>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ team: TTeam }, Error, TUpdateTeamRequest & { teamId: string }>(
    [MutationKeys.updateTeam],
    ({ teamId, ...data }: TUpdateTeamRequest & { teamId: string }) =>
      dataService.updateTeam(teamId, data),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teams]);
        queryClient.invalidateQueries([QueryKeys.team, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useDeleteTeamMutation = (
  options?: UseMutationOptions<{ success: boolean }, Error, string>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ success: boolean }, Error, string>(
    [MutationKeys.deleteTeam],
    (teamId: string) => dataService.deleteTeam(teamId),
    {
      ...options,
      onSuccess: (data, teamId, context) => {
        queryClient.invalidateQueries([QueryKeys.teams]);
        queryClient.invalidateQueries([QueryKeys.team, teamId]);
        options?.onSuccess?.(data, teamId, context);
      },
    },
  );
};

export const useRemoveMemberMutation = (
  options?: UseMutationOptions<{ success: boolean }, Error, TRemoveMemberRequest>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ success: boolean }, Error, TRemoveMemberRequest>(
    [MutationKeys.removeMember],
    ({ teamId, userId }: TRemoveMemberRequest) => dataService.removeTeamMember(teamId, userId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamMembers, variables.teamId]);
        queryClient.invalidateQueries([QueryKeys.team, variables.teamId]);
        queryClient.invalidateQueries([QueryKeys.teams]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useChangeMemberRoleMutation = (
  options?: UseMutationOptions<{ team: TTeam }, Error, TChangeMemberRoleRequest>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ team: TTeam }, Error, TChangeMemberRoleRequest>(
    [MutationKeys.changeMemberRole],
    ({ teamId, userId, role }: TChangeMemberRoleRequest) =>
      dataService.changeTeamMemberRole(teamId, userId, role),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamMembers, variables.teamId]);
        queryClient.invalidateQueries([QueryKeys.team, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useTransferOwnershipMutation = (
  options?: UseMutationOptions<{ team: TTeam }, Error, TTransferOwnershipRequest>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ team: TTeam }, Error, TTransferOwnershipRequest>(
    [MutationKeys.transferOwnership],
    ({ teamId, newOwnerId }: TTransferOwnershipRequest) =>
      dataService.transferTeamOwnership(teamId, newOwnerId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teams]);
        queryClient.invalidateQueries([QueryKeys.team, variables.teamId]);
        queryClient.invalidateQueries([QueryKeys.teamMembers, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useCreateInviteMutation = (
  options?: UseMutationOptions<
    { invite: TTeamInvite },
    Error,
    TCreateInviteRequest & { teamId: string }
  >,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ invite: TTeamInvite }, Error, TCreateInviteRequest & { teamId: string }>(
    [MutationKeys.createTeamInvite],
    ({ teamId, ...data }: TCreateInviteRequest & { teamId: string }) =>
      dataService.createTeamInvite(teamId, data),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamInvites, variables.teamId]);
        queryClient.invalidateQueries([QueryKeys.myTeamInvites]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useRevokeInviteMutation = (
  options?: UseMutationOptions<{ success: boolean }, Error, TRevokeInviteRequest>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ success: boolean }, Error, TRevokeInviteRequest>(
    [MutationKeys.revokeTeamInvite],
    ({ teamId, inviteId }: TRevokeInviteRequest) => dataService.revokeTeamInvite(teamId, inviteId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamInvites, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useAcceptInviteMutation = (
  options?: UseMutationOptions<{ team: TTeam }, Error, string>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ team: TTeam }, Error, string>(
    [MutationKeys.acceptTeamInvite],
    (token: string) => dataService.acceptTeamInvite(token),
    {
      ...options,
      onSuccess: (...params) => {
        queryClient.invalidateQueries([QueryKeys.teams]);
        queryClient.invalidateQueries([QueryKeys.myTeamInvites]);
        options?.onSuccess?.(...params);
      },
    },
  );
};

export const useDeclineInviteMutation = (
  options?: UseMutationOptions<{ success: boolean }, Error, string>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ success: boolean }, Error, string>(
    [MutationKeys.declineTeamInvite],
    (token: string) => dataService.declineTeamInvite(token),
    {
      ...options,
      onSuccess: (...params) => {
        queryClient.invalidateQueries([QueryKeys.myTeamInvites]);
        options?.onSuccess?.(...params);
      },
    },
  );
};

export const useAddKnowledgeMutation = (
  options?: UseMutationOptions<
    { success: boolean; fileId: string },
    Error,
    TAddKnowledgeRequest & { targetSubgroupId?: string }
  >,
) => {
  const queryClient = useQueryClient();
  return useMutation<
    { success: boolean; fileId: string },
    Error,
    TAddKnowledgeRequest & { targetSubgroupId?: string }
  >(
    [MutationKeys.addTeamKnowledge],
    ({ teamId, fileId, targetSubgroupId }: TAddKnowledgeRequest & { targetSubgroupId?: string }) =>
      dataService.addTeamKnowledge(teamId, fileId, targetSubgroupId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamKnowledge, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useRemoveKnowledgeMutation = (
  options?: UseMutationOptions<
    { success: boolean },
    Error,
    TRemoveKnowledgeRequest & { targetSubgroupId?: string }
  >,
) => {
  const queryClient = useQueryClient();
  return useMutation<
    { success: boolean },
    Error,
    TRemoveKnowledgeRequest & { targetSubgroupId?: string }
  >(
    [MutationKeys.removeTeamKnowledge],
    ({
      teamId,
      fileId,
      targetSubgroupId,
    }: TRemoveKnowledgeRequest & { targetSubgroupId?: string }) =>
      dataService.removeTeamKnowledge(teamId, fileId, targetSubgroupId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamKnowledge, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useShareAgentMutation = (
  options?: UseMutationOptions<
    { success: boolean; id: string },
    Error,
    TShareAgentRequest & { targetSubgroupId?: string }
  >,
) => {
  const queryClient = useQueryClient();
  return useMutation<
    { success: boolean; id: string },
    Error,
    TShareAgentRequest & { targetSubgroupId?: string }
  >(
    [MutationKeys.shareTeamAgent],
    ({ teamId, agentId, targetSubgroupId }: TShareAgentRequest & { targetSubgroupId?: string }) =>
      dataService.shareTeamAgent(teamId, agentId, targetSubgroupId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamAgents, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useUnshareAgentMutation = (
  options?: UseMutationOptions<
    { success: boolean },
    Error,
    TUnshareAgentRequest & { targetSubgroupId?: string }
  >,
) => {
  const queryClient = useQueryClient();
  return useMutation<
    { success: boolean },
    Error,
    TUnshareAgentRequest & { targetSubgroupId?: string }
  >(
    [MutationKeys.unshareTeamAgent],
    ({ teamId, agentId, targetSubgroupId }: TUnshareAgentRequest & { targetSubgroupId?: string }) =>
      dataService.unshareTeamAgent(teamId, agentId, targetSubgroupId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamAgents, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useSharePromptMutation = (
  options?: UseMutationOptions<
    { success: boolean; id: string },
    Error,
    TSharePromptRequest & { targetSubgroupId?: string }
  >,
) => {
  const queryClient = useQueryClient();
  return useMutation<
    { success: boolean; id: string },
    Error,
    TSharePromptRequest & { targetSubgroupId?: string }
  >(
    [MutationKeys.shareTeamPrompt],
    ({
      teamId,
      promptGroupId,
      targetSubgroupId,
    }: TSharePromptRequest & { targetSubgroupId?: string }) =>
      dataService.shareTeamPrompt(teamId, promptGroupId, targetSubgroupId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamPrompts, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useUnsharePromptMutation = (
  options?: UseMutationOptions<
    { success: boolean },
    Error,
    TUnsharePromptRequest & { targetSubgroupId?: string }
  >,
) => {
  const queryClient = useQueryClient();
  return useMutation<
    { success: boolean },
    Error,
    TUnsharePromptRequest & { targetSubgroupId?: string }
  >(
    [MutationKeys.unshareTeamPrompt],
    ({
      teamId,
      promptGroupId,
      targetSubgroupId,
    }: TUnsharePromptRequest & { targetSubgroupId?: string }) =>
      dataService.unshareTeamPrompt(teamId, promptGroupId, targetSubgroupId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.teamPrompts, variables.teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useCreateSubgroupMutation = (
  teamId: string,
  options?: UseMutationOptions<{ subgroup: TSubgroup }, Error, TCreateSubgroupRequest>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ subgroup: TSubgroup }, Error, TCreateSubgroupRequest>(
    [MutationKeys.createSubgroup],
    (body: TCreateSubgroupRequest) => dataService.createSubgroup(teamId, body),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.subgroups, teamId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useUpdateSubgroupMutation = (
  teamId: string,
  options?: UseMutationOptions<
    { subgroup: TSubgroup },
    Error,
    TUpdateSubgroupRequest & { sgId: string }
  >,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ subgroup: TSubgroup }, Error, TUpdateSubgroupRequest & { sgId: string }>(
    [MutationKeys.updateSubgroup],
    ({ sgId, ...body }: TUpdateSubgroupRequest & { sgId: string }) =>
      dataService.updateSubgroup(teamId, sgId, body),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.subgroups, teamId]);
        queryClient.invalidateQueries([QueryKeys.subgroup, teamId, variables.sgId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useDeleteSubgroupMutation = (
  teamId: string,
  options?: UseMutationOptions<{ success: boolean }, Error, string>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ success: boolean }, Error, string>(
    [MutationKeys.deleteSubgroup],
    (sgId: string) => dataService.deleteSubgroup(teamId, sgId),
    {
      ...options,
      onSuccess: (data, sgId, context) => {
        queryClient.invalidateQueries([QueryKeys.subgroups, teamId]);
        queryClient.invalidateQueries([QueryKeys.subgroup, teamId, sgId]);
        queryClient.invalidateQueries([QueryKeys.teamKnowledge, teamId]);
        queryClient.invalidateQueries([QueryKeys.teamAgents, teamId]);
        queryClient.invalidateQueries([QueryKeys.teamPrompts, teamId]);
        options?.onSuccess?.(data, sgId, context);
      },
    },
  );
};

export const useAddSubgroupMemberMutation = (
  teamId: string,
  options?: UseMutationOptions<{ success: boolean }, Error, { sgId: string; userId: string }>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ success: boolean }, Error, { sgId: string; userId: string }>(
    [MutationKeys.addSubgroupMember],
    ({ sgId, userId }: { sgId: string; userId: string }) =>
      dataService.addSubgroupMember(teamId, sgId, userId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.subgroups, teamId]);
        queryClient.invalidateQueries([QueryKeys.subgroup, teamId, variables.sgId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};

export const useRemoveSubgroupMemberMutation = (
  teamId: string,
  options?: UseMutationOptions<{ success: boolean }, Error, { sgId: string; userId: string }>,
) => {
  const queryClient = useQueryClient();
  return useMutation<{ success: boolean }, Error, { sgId: string; userId: string }>(
    [MutationKeys.removeSubgroupMember],
    ({ sgId, userId }: { sgId: string; userId: string }) =>
      dataService.removeSubgroupMember(teamId, sgId, userId),
    {
      ...options,
      onSuccess: (data, variables, context) => {
        queryClient.invalidateQueries([QueryKeys.subgroups, teamId]);
        queryClient.invalidateQueries([QueryKeys.subgroup, teamId, variables.sgId]);
        options?.onSuccess?.(data, variables, context);
      },
    },
  );
};
