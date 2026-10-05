import { useQuery } from '@tanstack/react-query';

export type Health = { name: string; ok: boolean; status?: number; ms: number; error?: string };
export type StatusResponse = { box: Record<string, unknown> & { name: string }; services: Health[] };

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin' });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw { error: (body as { error?: string }).error ?? `HTTP ${r.status}` };
  return body as T;
}

export const useStatus = () => useQuery({ queryKey: ['status'], queryFn: () => get<StatusResponse>('/api/status') });
