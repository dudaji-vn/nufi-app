import React, { useState } from 'react';
import { File, Plus, Trash2 } from 'lucide-react';
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
import type { TTeamKnowledgeListResponse, TeamRole, TSubgroup } from 'librechat-data-provider';
import type { TFile } from 'librechat-data-provider';
import {
  useTeamKnowledgeQuery,
  useAddKnowledgeMutation,
  useRemoveKnowledgeMutation,
  useSubgroupsQuery,
} from '~/data-provider';
import { useGetFiles } from '~/data-provider';
import { useLocalize } from '~/hooks';

type TTeamKnowledgeRow = TTeamKnowledgeListResponse['files'][number];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface FilePickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  teamId: string;
  sharedFiles: TTeamKnowledgeRow[];
}

function FilePickerDialog({ open, onOpenChange, teamId, sharedFiles }: FilePickerDialogProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const { data: files = [] } = useGetFiles<TFile[]>();
  const { data: subgroupsData } = useSubgroupsQuery(teamId, { enabled: open });
  const [targetSubgroupId, setTargetSubgroupId] = useState<string | undefined>(undefined);

  const subgroups: TSubgroup[] = subgroupsData?.subgroups ?? [];

  const { mutate: addKnowledge, isLoading } = useAddKnowledgeMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_file_added'), status: 'success' });
      onOpenChange(false);
    },
    onError: (error: Error) => {
      const msg =
        error.message?.includes('409') || error.message?.toLowerCase().includes('temporary')
          ? localize('com_ui_team_file_temp_error')
          : error.message || localize('com_ui_error');
      showToast({ message: msg, status: 'error' });
    },
  });

  const sharedKeys = new Set(
    sharedFiles.map((r) => `${r.file_id}-${r.target.type === 'subgroup' ? r.target.id : 'team'}`),
  );
  const selectedKey = targetSubgroupId ?? 'team';
  const availableFiles = files.filter((f) => !sharedKeys.has(`${f.file_id}-${selectedKey}`));

  return (
    <OGDialog open={open} onOpenChange={onOpenChange}>
      <OGDialogContent className="w-11/12 md:max-w-lg">
        <OGDialogHeader>
          <OGDialogTitle>{localize('com_ui_team_select_file')}</OGDialogTitle>
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
        {availableFiles.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-secondary">
            {localize('com_ui_team_no_knowledge')}
          </p>
        ) : (
          <ul className="flex max-h-80 flex-col gap-1 overflow-y-auto py-2">
            {availableFiles.map((file) => (
              <li
                key={file.file_id}
                className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 hover:bg-surface-hover"
              >
                <div className="flex min-w-0 flex-1 items-center gap-3">
                  <File className="size-4 shrink-0 text-text-secondary" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-text-primary">
                      {file.filename}
                    </p>
                    <p className="text-xs text-text-secondary">{formatBytes(file.bytes)}</p>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isLoading}
                  onClick={() => addKnowledge({ teamId, fileId: file.file_id, targetSubgroupId })}
                  aria-label={localize('com_ui_team_add_file')}
                >
                  {isLoading ? <Spinner className="size-3.5" /> : localize('com_ui_team_add_file')}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </OGDialogContent>
    </OGDialog>
  );
}

interface KnowledgeRowProps {
  file: TTeamKnowledgeRow;
  teamId: string;
  canManage: boolean;
}

function KnowledgeRow({ file, teamId, canManage }: KnowledgeRowProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();

  const { mutate: removeKnowledge, isLoading } = useRemoveKnowledgeMutation({
    onSuccess: () => {
      showToast({ message: localize('com_ui_team_file_removed'), status: 'success' });
    },
    onError: (error: Error) => {
      showToast({ message: error.message || localize('com_ui_error'), status: 'error' });
    },
  });

  const targetSubgroupId = file.target.type === 'subgroup' ? file.target.id : undefined;

  return (
    <li className="flex items-center justify-between gap-3 rounded-lg border border-border-light bg-surface-primary px-3.5 py-2.5">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-tertiary">
          <File className="size-4 text-text-secondary" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-text-primary">{file.filename}</p>
          <p className="text-xs text-text-secondary">
            {formatBytes(file.bytes)}
            {file.type && (
              <span className="ml-2 rounded bg-surface-tertiary px-1 py-0.5 font-mono text-[10px]">
                {file.type}
              </span>
            )}
          </p>
        </div>
        <span className="rounded-full bg-surface-tertiary px-2 py-0.5 text-xs text-text-secondary">
          {file.target.type === 'subgroup' ? file.target.name : localize('com_ui_team_whole_team')}
        </span>
      </div>
      {canManage && (
        <Button
          variant="outline"
          size="sm"
          disabled={isLoading}
          onClick={() => removeKnowledge({ teamId, fileId: file.file_id, targetSubgroupId })}
          aria-label={localize('com_ui_team_remove_file')}
        >
          {isLoading ? (
            <Spinner className="size-3.5" />
          ) : (
            <Trash2 className="size-3.5" aria-hidden="true" />
          )}
        </Button>
      )}
    </li>
  );
}

interface KnowledgeTabProps {
  teamId: string;
  callerRole: TeamRole;
}

export default function KnowledgeTab({ teamId, callerRole }: KnowledgeTabProps) {
  const localize = useLocalize();
  const [pickerOpen, setPickerOpen] = useState(false);
  const canManage = callerRole === 'owner' || callerRole === 'admin';
  const { data, isLoading } = useTeamKnowledgeQuery(teamId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner className="text-text-secondary" aria-label={localize('com_ui_loading')} />
      </div>
    );
  }

  const files = data?.files ?? [];

  return (
    <section aria-label={localize('com_ui_team_knowledge')} className="flex flex-col gap-4">
      {canManage && (
        <div className="flex justify-end">
          <Button
            variant="submit"
            className="gap-1.5 text-white"
            onClick={() => setPickerOpen(true)}
            aria-label={localize('com_ui_team_add_file')}
          >
            <Plus className="size-4" aria-hidden="true" />
            {localize('com_ui_team_add_file')}
          </Button>
        </div>
      )}

      {files.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border-light py-12 text-center">
          <File className="size-8 text-text-tertiary" aria-hidden="true" />
          <p className="text-sm text-text-secondary">{localize('com_ui_team_no_knowledge')}</p>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {files.map((file) => (
            <KnowledgeRow
              key={`${file.file_id}-${file.target.type === 'subgroup' ? file.target.id : 'team'}`}
              file={file}
              teamId={teamId}
              canManage={canManage}
            />
          ))}
        </ul>
      )}

      {canManage && (
        <FilePickerDialog
          open={pickerOpen}
          onOpenChange={setPickerOpen}
          teamId={teamId}
          sharedFiles={files}
        />
      )}
    </section>
  );
}
