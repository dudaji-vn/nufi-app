import { Bot, BookOpen, Unlink } from 'lucide-react';
import { Button, Spinner, useToastContext } from '@librechat/client';
import type { TTeamAgentInfo, TTeamPromptGroupInfo, TeamRole } from 'librechat-data-provider';
import {
  useTeamAgentsQuery,
  useTeamPromptsQuery,
  useUnshareAgentMutation,
  useUnsharePromptMutation,
} from '~/data-provider';
import { useLocalize } from '~/hooks';

interface AgentRowProps {
  agent: TTeamAgentInfo;
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

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-4 py-3">
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
      </div>
      {canManage && (
        <Button
          variant="outline"
          size="sm"
          disabled={isLoading}
          onClick={() => unshareAgent({ teamId, agentId: agent.id })}
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
  prompt: TTeamPromptGroupInfo;
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

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-4 py-3">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-tertiary">
          <BookOpen className="size-4 text-text-secondary" aria-hidden="true" />
        </div>
        <p className="truncate text-sm font-medium text-text-primary">{prompt.name}</p>
      </div>
      {canManage && (
        <Button
          variant="outline"
          size="sm"
          disabled={isLoading}
          onClick={() => unsharePrompt({ teamId, promptGroupId: prompt.id })}
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

interface SharedTabProps {
  teamId: string;
  callerRole: TeamRole;
}

export default function SharedTab({ teamId, callerRole }: SharedTabProps) {
  const localize = useLocalize();
  const canManage = callerRole === 'owner' || callerRole === 'admin';

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
        <h3 className="text-sm font-semibold text-text-primary">
          {localize('com_ui_team_shared_agents')}
        </h3>
        {agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-light py-8 text-center">
            <Bot className="size-7 text-text-tertiary" aria-hidden="true" />
            <p className="text-sm text-text-secondary">{localize('com_ui_team_no_shared')}</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {agents.map((agent) => (
              <AgentRow key={agent.id} agent={agent} teamId={teamId} canManage={canManage} />
            ))}
          </ul>
        )}
      </section>

      <section aria-label={localize('com_ui_team_shared_prompts')} className="flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-text-primary">
          {localize('com_ui_team_shared_prompts')}
        </h3>
        {prompts.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-light py-8 text-center">
            <BookOpen className="size-7 text-text-tertiary" aria-hidden="true" />
            <p className="text-sm text-text-secondary">{localize('com_ui_team_no_shared')}</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {prompts.map((prompt) => (
              <PromptRow key={prompt.id} prompt={prompt} teamId={teamId} canManage={canManage} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
