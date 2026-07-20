import { useState } from 'react';
import { Bot, BookOpen, Unlink, Plus } from 'lucide-react';
import {
  Button,
  Spinner,
  useToastContext,
  OGDialog,
  OGDialogContent,
  OGDialogHeader,
  OGDialogTitle,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@librechat/client';
import type {
  TeamRole,
  TSubgroup,
  TTeamAgentsListResponse,
  TTeamPromptsListResponse,
} from 'librechat-data-provider';
import {
  useTeamAgentsQuery,
  useTeamPromptsQuery,
  useShareAgentMutation,
  useUnshareAgentMutation,
  useSharePromptMutation,
  useUnsharePromptMutation,
  useListAgentsQuery,
  useGetAllPromptGroups,
  useSubgroupsQuery,
} from '~/data-provider';
import { useLocalize } from '~/hooks';

type TTeamAgentRow = TTeamAgentsListResponse['resources'][number];
type TTeamPromptRow = TTeamPromptsListResponse['resources'][number];

interface AgentRowProps {
  agent: TTeamAgentRow;
  teamId: string;
  canManage: boolean;
}

function AgentRow({ agent, teamId, canManage }: AgentRowProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();

  const { mutate: unshareAgent, isLoading } = useUnshareAgentMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_unshare'), status: 'success' });
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const targetSubgroupId = agent.target.type === 'subgroup' ? agent.target.id : undefined;

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-3.5 py-2.5">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-tertiary">
          <Bot className="size-4 text-text-secondary" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-text-primary">{agent.name ?? agent.id}</p>
          {agent.description != null && agent.description !== '' && (
            <p className="truncate text-xs text-text-secondary">{agent.description}</p>
          )}
        </div>
        <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-xs text-text-secondary">
          {agent.target.type === 'subgroup'
            ? agent.target.name
            : localize('com_ui_team_whole_team')}
        </span>
      </div>
      {canManage && (
        <Button
          variant="outline"
          size="sm"
          disabled={isLoading}
          onClick={() => unshareAgent({ teamId, agentId: agent.id, targetSubgroupId })}
          aria-label={localize('com_ui_team_unshare')}
        >
          {isLoading ? (
            <Spinner className="size-3.5" />
          ) : (
            <Unlink className="size-3.5" aria-hidden="true" />
          )}
        </Button>
      )}
    </li>
  );
}

interface PromptRowProps {
  prompt: TTeamPromptRow;
  teamId: string;
  canManage: boolean;
}

function PromptRow({ prompt, teamId, canManage }: PromptRowProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();

  const { mutate: unsharePrompt, isLoading } = useUnsharePromptMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_unshare'), status: 'success' });
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const targetSubgroupId = prompt.target.type === 'subgroup' ? prompt.target.id : undefined;

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-3.5 py-2.5">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-tertiary">
          <BookOpen className="size-4 text-text-secondary" aria-hidden="true" />
        </div>
        <p className="truncate text-sm font-medium text-text-primary">{prompt.name}</p>
        <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-xs text-text-secondary">
          {prompt.target.type === 'subgroup'
            ? prompt.target.name
            : localize('com_ui_team_whole_team')}
        </span>
      </div>
      {canManage && (
        <Button
          variant="outline"
          size="sm"
          disabled={isLoading}
          onClick={() => unsharePrompt({ teamId, promptGroupId: prompt.id, targetSubgroupId })}
          aria-label={localize('com_ui_team_unshare')}
        >
          {isLoading ? (
            <Spinner className="size-3.5" />
          ) : (
            <Unlink className="size-3.5" aria-hidden="true" />
          )}
        </Button>
      )}
    </li>
  );
}

interface AgentPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  teamId: string;
  sharedAgents: TTeamAgentRow[];
}

function AgentPickerDialog({ open, onOpenChange, teamId, sharedAgents }: AgentPickerDialogProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const { data } = useListAgentsQuery(undefined, { enabled: open });
  const { data: subgroupsData } = useSubgroupsQuery(teamId, { enabled: open });
  const [targetSubgroupId, setTargetSubgroupId] = useState<string | undefined>(undefined);

  const subgroups: TSubgroup[] = subgroupsData?.subgroups ?? [];

  const { mutate: shareAgent, isLoading } = useShareAgentMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_agent_shared'), status: 'success' });
      onOpenChange(false);
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const sharedKeys = new Set(
    sharedAgents.map((r) => `${r.id}-${r.target.type === 'subgroup' ? r.target.id : 'team'}`),
  );
  const selectedKey = targetSubgroupId ?? 'team';
  const available = (data?.data ?? []).filter(
    (agent) => !sharedKeys.has(`${agent.id}-${selectedKey}`),
  );

  return (
    <OGDialog open={open} onOpenChange={onOpenChange}>
      <OGDialogContent className="w-11/12 md:max-w-lg">
        <OGDialogHeader>
          <OGDialogTitle>{localize('com_ui_team_select_agent')}</OGDialogTitle>
        </OGDialogHeader>
        {subgroups.length > 0 && (
          <div className="px-1 pb-2">
            <p className="mb-1.5 text-sm font-medium text-text-primary">
              {localize('com_ui_team_share_with')}
            </p>
            <Select
              value={targetSubgroupId ?? 'team'}
              onValueChange={(v) => setTargetSubgroupId(v === 'team' ? undefined : v)}
            >
              <SelectTrigger className="w-full" aria-label={localize('com_ui_team_share_with')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="z-[200]">
                <SelectItem value="team">{localize('com_ui_team_whole_team')}</SelectItem>
                {subgroups.map((sg) => (
                  <SelectItem key={sg._id} value={sg._id}>
                    {sg.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {available.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-secondary">
            {localize('com_ui_team_no_agents_to_share')}
          </p>
        ) : (
          <ul className="flex max-h-80 flex-col gap-1 overflow-y-auto py-2">
            {available.map((agent) => (
              <li
                key={agent.id}
                className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 hover:bg-surface-hover"
              >
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <Bot className="size-4 shrink-0 text-text-secondary" aria-hidden="true" />
                  <p className="truncate text-sm font-medium text-text-primary">
                    {agent.name ?? agent.id}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isLoading}
                  onClick={() => shareAgent({ teamId, agentId: agent.id, targetSubgroupId })}
                  aria-label={localize('com_ui_add')}
                >
                  {isLoading ? <Spinner className="size-3.5" /> : localize('com_ui_add')}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </OGDialogContent>
    </OGDialog>
  );
}

interface PromptPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  teamId: string;
  sharedPrompts: TTeamPromptRow[];
}

function PromptPickerDialog({
  open,
  onOpenChange,
  teamId,
  sharedPrompts,
}: PromptPickerDialogProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const { data } = useGetAllPromptGroups(undefined, { enabled: open });
  const { data: subgroupsData } = useSubgroupsQuery(teamId, { enabled: open });
  const [targetSubgroupId, setTargetSubgroupId] = useState<string | undefined>(undefined);

  const subgroups: TSubgroup[] = subgroupsData?.subgroups ?? [];

  const { mutate: sharePrompt, isLoading } = useSharePromptMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_prompt_shared'), status: 'success' });
      onOpenChange(false);
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const sharedKeys = new Set(
    sharedPrompts.map((r) => `${r.id}-${r.target.type === 'subgroup' ? r.target.id : 'team'}`),
  );
  const selectedKey = targetSubgroupId ?? 'team';
  const available = (data ?? []).filter(
    (group) => group._id != null && !sharedKeys.has(`${group._id}-${selectedKey}`),
  );

  return (
    <OGDialog open={open} onOpenChange={onOpenChange}>
      <OGDialogContent className="w-11/12 md:max-w-lg">
        <OGDialogHeader>
          <OGDialogTitle>{localize('com_ui_team_select_prompt')}</OGDialogTitle>
        </OGDialogHeader>
        {subgroups.length > 0 && (
          <div className="px-1 pb-2">
            <p className="mb-1.5 text-sm font-medium text-text-primary">
              {localize('com_ui_team_share_with')}
            </p>
            <Select
              value={targetSubgroupId ?? 'team'}
              onValueChange={(v) => setTargetSubgroupId(v === 'team' ? undefined : v)}
            >
              <SelectTrigger className="w-full" aria-label={localize('com_ui_team_share_with')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="z-[200]">
                <SelectItem value="team">{localize('com_ui_team_whole_team')}</SelectItem>
                {subgroups.map((sg) => (
                  <SelectItem key={sg._id} value={sg._id}>
                    {sg.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {available.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-secondary">
            {localize('com_ui_team_no_prompts_to_share')}
          </p>
        ) : (
          <ul className="flex max-h-80 flex-col gap-1 overflow-y-auto py-2">
            {available.map((group) => (
              <li
                key={group._id}
                className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 hover:bg-surface-hover"
              >
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <BookOpen className="size-4 shrink-0 text-text-secondary" aria-hidden="true" />
                  <p className="truncate text-sm font-medium text-text-primary">{group.name}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isLoading}
                  onClick={() =>
                    sharePrompt({
                      teamId,
                      promptGroupId: group._id as string,
                      targetSubgroupId,
                    })
                  }
                  aria-label={localize('com_ui_add')}
                >
                  {isLoading ? <Spinner className="size-3.5" /> : localize('com_ui_add')}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </OGDialogContent>
    </OGDialog>
  );
}

interface SharedTabProps {
  teamId: string;
  callerRole: TeamRole;
}

export default function SharedTab({ teamId, callerRole }: SharedTabProps) {
  const localize = useLocalize();
  const canManage = callerRole === 'owner' || callerRole === 'admin';
  const [agentPickerOpen, setAgentPickerOpen] = useState(false);
  const [promptPickerOpen, setPromptPickerOpen] = useState(false);

  const { data: agentsData, isLoading: isLoadingAgents } = useTeamAgentsQuery(teamId);
  const { data: promptsData, isLoading: isLoadingPrompts } = useTeamPromptsQuery(teamId);

  const agents = agentsData?.resources ?? [];
  const prompts = promptsData?.resources ?? [];

  const isLoading = isLoadingAgents || isLoadingPrompts;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner className="text-text-secondary" aria-label={localize('com_ui_loading')} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <section aria-label={localize('com_ui_team_shared_agents')} className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary">
            {localize('com_ui_team_shared_agents')}
          </h3>
          {canManage && (
            <Button
              variant="submit"
              size="sm"
              className="gap-1.5 text-white"
              onClick={() => setAgentPickerOpen(true)}
              aria-label={localize('com_ui_team_add_agent')}
            >
              <Plus className="size-4" aria-hidden="true" />
              {localize('com_ui_team_add_agent')}
            </Button>
          )}
        </div>
        {agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-light py-8 text-center">
            <Bot className="size-7 text-text-tertiary" aria-hidden="true" />
            <p className="text-sm text-text-secondary">{localize('com_ui_team_no_shared')}</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {agents.map((agent) => (
              <AgentRow
                key={`${agent.id}-${agent.target.type === 'subgroup' ? agent.target.id : 'team'}`}
                agent={agent}
                teamId={teamId}
                canManage={canManage}
              />
            ))}
          </ul>
        )}
      </section>

      <section aria-label={localize('com_ui_team_shared_prompts')} className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary">
            {localize('com_ui_team_shared_prompts')}
          </h3>
          {canManage && (
            <Button
              variant="submit"
              size="sm"
              className="gap-1.5 text-white"
              onClick={() => setPromptPickerOpen(true)}
              aria-label={localize('com_ui_team_add_prompt')}
            >
              <Plus className="size-4" aria-hidden="true" />
              {localize('com_ui_team_add_prompt')}
            </Button>
          )}
        </div>
        {prompts.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-light py-8 text-center">
            <BookOpen className="size-7 text-text-tertiary" aria-hidden="true" />
            <p className="text-sm text-text-secondary">{localize('com_ui_team_no_shared')}</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {prompts.map((prompt) => (
              <PromptRow
                key={`${prompt.id}-${prompt.target.type === 'subgroup' ? prompt.target.id : 'team'}`}
                prompt={prompt}
                teamId={teamId}
                canManage={canManage}
              />
            ))}
          </ul>
        )}
      </section>

      {canManage && (
        <>
          <AgentPickerDialog
            open={agentPickerOpen}
            onOpenChange={setAgentPickerOpen}
            teamId={teamId}
            sharedAgents={agents}
          />
          <PromptPickerDialog
            open={promptPickerOpen}
            onOpenChange={setPromptPickerOpen}
            teamId={teamId}
            sharedPrompts={prompts}
          />
        </>
      )}
    </div>
  );
}
