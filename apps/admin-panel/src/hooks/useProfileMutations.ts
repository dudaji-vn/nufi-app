import { useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { PrincipalType } from 'librechat-data-provider';
import type * as t from '@/types';
import { removeFieldProfileValueFn, saveFieldProfileValueFn } from '@/server';

export function useProfileMutations({
  fieldPath,
  onProfileChange,
}: t.UseProfileMutationsOptions): t.UseProfileMutationsReturn {
  const queryClient = useQueryClient();

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['profileMap'] });
    queryClient.invalidateQueries({ queryKey: ['resolvedConfig'] });
    queryClient.invalidateQueries({ queryKey: ['availableScopes'] });
    onProfileChange?.();
  }, [queryClient, onProfileChange]);

  const saveMutation = useMutation({
    mutationFn: (params: { principalType: PrincipalType; principalId: string; value: unknown }) =>
      saveFieldProfileValueFn({ data: { fieldPath, ...params } }),
    onSuccess: () => invalidate(),
  });

  const removeMutation = useMutation({
    mutationFn: (params: { principalType: PrincipalType; principalId: string }) =>
      removeFieldProfileValueFn({ data: { fieldPath, ...params } }),
    onSuccess: () => invalidate(),
  });

  return {
    saveMutation,
    removeMutation,
    saving: saveMutation.isPending || removeMutation.isPending,
  };
}
