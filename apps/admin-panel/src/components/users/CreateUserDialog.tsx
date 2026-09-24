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
  const [createdPassword, setCreatedPassword] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => createUserFn({ data: { name, email, role } }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setCreatedPassword(result.password);
    },
    onError: (err: Error) => setError(err.message),
  });

  const resetAndClose = () => {
    setName('');
    setEmail('');
    setRole(SystemRoles.USER);
    setError('');
    setCreatedPassword(null);
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
      submitLabel={createdPassword != null ? localize('com_ui_done') : localize('com_users_add')}
      submitDisabled={createdPassword != null ? false : !name.trim() || !email.trim()}
      saving={mutation.isPending}
      error={error}
      onSubmit={createdPassword != null ? resetAndClose : doSubmit}
      onClose={resetAndClose}
    >
      {createdPassword != null ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-foreground">{localize('com_users_created_title')}</p>
          <label className="text-sm font-medium text-foreground">
            {localize('com_users_temp_password')}
          </label>
          <code className="select-all rounded-lg border border-border bg-muted px-3 py-2 font-mono text-sm text-foreground">
            {createdPassword}
          </code>
          <p className="text-xs text-muted-foreground">
            {localize('com_users_temp_password_hint')}
          </p>
        </div>
      ) : (
        <>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="user-name" className="text-sm font-medium text-foreground">
          {localize('com_access_col_name')}
        </label>
        <input
          id="user-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={localize('com_users_name_placeholder')}
          autoFocus
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="user-email" className="text-sm font-medium text-foreground">
          {localize('com_auth_email_label')}
        </label>
        <input
          id="user-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={localize('com_users_email_placeholder')}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="user-role" className="text-sm font-medium text-foreground">
          {localize('com_users_role_label')}
        </label>
        <select
          id="user-role"
          value={role}
          onChange={(e) => setRole(e.target.value as SystemRoles)}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
        >
          <option value={SystemRoles.USER}>{SystemRoles.USER}</option>
          <option value={SystemRoles.ADMIN}>{SystemRoles.ADMIN}</option>
        </select>
      </div>
        </>
      )}
    </FormDialog>
  );
}
