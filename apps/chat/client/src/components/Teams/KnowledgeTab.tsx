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
} from '@librechat/client';
import type { TTeamKnowledgeFile, TeamRole } from 'librechat-data-provider';
import type { TFile } from 'librechat-data-provider';
import {
  useTeamKnowledgeQuery,
  useAddKnowledgeMutation,
  useRemoveKnowledgeMutation,
} from '~/data-provider';
import { useGetFiles } from '~/data-provider';
import { useLocalize } from '~/hooks';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface FilePickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  teamId: string;
  sharedFileIds: Set<string>;
}

function FilePickerDialog({ open, onOpenChange, teamId, sharedFileIds }: FilePickerDialogProps) {
  const localize = useLocalize();
  const { showToast } = useToastContext();
  const { data: files = [] } = useGetFiles<TFile[]>();

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

  const availableFiles = files.filter((f) => !sharedFileIds.has(f.file_id));

  return (
    <OGDialog open={open} onOpenChange={onOpenChange}>
      <OGDialogContent className="w-11/12 md:max-w-lg">
        <OGDialogHeader>
          <OGDialogTitle>{localize('com_ui_team_select_file')}</OGDialogTitle>
        </OGDialogHeader>
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
                  onClick={() => addKnowledge({ teamId, fileId: file.file_id })}
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
  file: TTeamKnowledgeFile;
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
      </div>
      {canManage && (
        <Button
          variant="outline"
          size="sm"
          disabled={isLoading}
          onClick={() => removeKnowledge({ teamId, fileId: file.file_id })}
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
  const sharedFileIds = new Set(files.map((f) => f.file_id));

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
            <KnowledgeRow key={file.file_id} file={file} teamId={teamId} canManage={canManage} />
          ))}
        </ul>
      )}

      {canManage && (
        <FilePickerDialog
          open={pickerOpen}
          onOpenChange={setPickerOpen}
          teamId={teamId}
          sharedFileIds={sharedFileIds}
        />
      )}
    </section>
  );
}
