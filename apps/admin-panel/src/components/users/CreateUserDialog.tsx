import { useState } from 'react';
import { SystemRoles } from 'librechat-data-provider';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type * as t from '@/types';
import { FormDialog } from '@/components/shared';
import { createUserFn } from '@/server';
import { useLocalize } from '@/hooks';

export function CreateUserDialog({ open, onClose }: t.CreateUserDialogProps) {
  const localize = useLocalize();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<SystemRoles>(SystemRoles.USER);
  const [error, setError] = useState('');

  const mutation = useMutation({
    mutationFn: () => createUserFn({ data: { name, email, role } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      resetAndClose();
    },
    onError: (err: Error) => setError(err.message),
  });

  const resetAndClose = () => {
    setName('');
    setEmail('');
    setRole(SystemRoles.USER);
    setError('');
    onClose();
  };

  const doSubmit = () => {
    setError('');
    if (!name.trim()) {
      setError(localize('com_access_name_required'));
      return;
    }
    if (!email.trim()) {
      setError(localize('com_users_email_required'));
      return;
    }
    mutation.mutate();
  };

  return (
    <FormDialog
      open={open}
      title={localize('com_users_add')}
      submitLabel={localize('com_users_add')}
      submitDisabled={!name.trim() || !email.trim()}
      saving={mutation.isPending}
      error={error}
      onSubmit={doSubmit}
      onClose={resetAndClose}
    >
      <div className="flex flex-col gap-1.5">
        <label htmlFor="user-name" className="text-sm font-medium text-(--cui-color-text-default)">
          {localize('com_access_col_name')}
        </label>
        <input
          id="user-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={localize('com_users_name_placeholder')}
          autoFocus
          className="rounded-lg border border-(--cui-color-stroke-default) bg-(--cui-color-background-default) px-3 py-2 text-sm text-(--cui-color-text-default) placeholder:text-(--cui-color-text-disabled)"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="user-email" className="text-sm font-medium text-(--cui-color-text-default)">
          {localize('com_auth_email_label')}
        </label>
        <input
          id="user-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={localize('com_users_email_placeholder')}
          className="rounded-lg border border-(--cui-color-stroke-default) bg-(--cui-color-background-default) px-3 py-2 text-sm text-(--cui-color-text-default) placeholder:text-(--cui-color-text-disabled)"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="user-role" className="text-sm font-medium text-(--cui-color-text-default)">
          {localize('com_users_role_label')}
        </label>
        <select
          id="user-role"
          value={role}
          onChange={(e) => setRole(e.target.value as SystemRoles)}
          className="rounded-lg border border-(--cui-color-stroke-default) bg-(--cui-color-background-default) px-3 py-2 text-sm text-(--cui-color-text-default)"
        >
          <option value={SystemRoles.USER}>{SystemRoles.USER}</option>
          <option value={SystemRoles.ADMIN}>{SystemRoles.ADMIN}</option>
        </select>
      </div>
    </FormDialog>
  );
}
