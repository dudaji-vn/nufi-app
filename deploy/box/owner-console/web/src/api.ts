import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

export type Health = { name: string; ok: boolean; status?: number; ms: number; error?: string };
export type StatusResponse = { box: Record<string, unknown> & { name: string }; services: Health[] };
export type ControlAction = 'start' | 'restart' | 'stop';
export type ControlRequest = { action: ControlAction; service: string };

// A 401 means the owner session is gone: send the browser to the login page.
function unauthorized(r: Response) {
  if (r.status === 401) window.location.assign('/login');
}

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin' });
  unauthorized(r);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw { error: (body as { error?: string }).error ?? `HTTP ${r.status}` };
  return body as T;
}

export async function post<T>(path: string, payload: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  unauthorized(r);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw { error: (body as { error?: string }).error ?? `HTTP ${r.status}` };
  return body as T;
}

export type UserOs = 'macos' | 'windows' | 'linux';
export type UserRow = {
  id: string; name: string; os: UserOs; keyId: string; token: string; createdAt: string;
  activation: 'pending' | 'activated' | 'expired'; expiresAt?: string; nodeIp?: string; online?: boolean;
};
export async function del<T>(path: string): Promise<T> { const r = await fetch(path, { method: 'DELETE', credentials: 'same-origin' }); unauthorized(r); const body = await r.json().catch(() => ({})); if (!r.ok) throw { error: (body as { error?: string }).error ?? `HTTP ${r.status}` }; return body as T; }
export const useStatus = () =>
  useQuery({ queryKey: ['status'], queryFn: () => get<StatusResponse>('/api/status'), retry: false });

export const useControl = () =>
  useMutation({ mutationFn: (req: ControlRequest) => post<{ ok: boolean; audit: string }>('/api/control', req) });

// POST /api/console and call onLine for each SSE `data:` line as it arrives.
// Rejects with {error} on a non-2xx response or an `error` event.
export async function streamConsole(cmd: string, onLine: (line: string) => void): Promise<void> {
  const r = await fetch('/api/console', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ cmd }),
  });
  unauthorized(r);
  if (!r.ok || !r.body) {
    const body = await r.json().catch(() => ({}));
    throw { error: (body as { error?: string }).error ?? `HTTP ${r.status}` };
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  const frame = (f: string) => {
    let event = 'message';
    const data: string[] = [];
    for (const l of f.split('\n')) {
      if (l.startsWith('event:')) event = l.slice(6).trim();
      else if (l.startsWith('data:')) data.push(l.slice(5).replace(/^ /, ''));
    }
    if (!data.length) return;
    if (event === 'error') throw { error: data.join('\n') };
    onLine(data.join('\n'));
  };
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const frames = buf.split('\n\n');
    buf = frames.pop() ?? '';
    frames.forEach(frame);
  }
  if (buf.trim()) frame(buf);
}

export const useUsers = () => useQuery({ queryKey: ['users'], queryFn: () => get<UserRow[]>('/api/users'), retry: false });
const useRefreshUsers = () => { const qc = useQueryClient(); return () => qc.invalidateQueries({ queryKey: ['users'] }); };
export const useAddUser = () => { const refresh = useRefreshUsers(); return useMutation({ mutationFn: (req: { name: string; os: UserOs }) => post<UserRow>('/api/users', req), onSuccess: refresh }); };
export const useDeleteUser = () => { const refresh = useRefreshUsers(); return useMutation({ mutationFn: (id: string) => del<unknown>('/api/users/' + encodeURIComponent(id)), onSuccess: refresh }); };
export const useRegenerate = () => { const refresh = useRefreshUsers(); return useMutation({ mutationFn: (id: string) => post<UserRow>('/api/users/' + encodeURIComponent(id) + '/regenerate', {}), onSuccess: refresh }); };
export const useImportUsers = () => {
  const refresh = useRefreshUsers();
  return useMutation({
    mutationFn: async (file: File) => {
      const r = await fetch('/api/users/import', { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'text/csv' }, body: file });
      unauthorized(r);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw { error: (body as { error?: string }).error ?? `HTTP ${r.status}` };
      return { added: (body as UserRow[]).length, skipped: Number(r.headers.get('X-Skipped') ?? 0) };
    },
    onSuccess: refresh,
  });
};
export async function exportUsersCsv(ids: string[]): Promise<void> {
  const r = await fetch('/api/users/export', { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ids }) });
  unauthorized(r);
  if (!r.ok) { const body = await r.json().catch(() => ({})); throw { error: (body as { error?: string }).error ?? `HTTP ${r.status}` }; }
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement('a');
  a.href = url; a.download = 'users.csv';
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
export const connectorUrl = (u: Pick<UserRow, 'id' | 'os'>) => `/api/users/${encodeURIComponent(u.id)}/connector?os=${u.os}`;
export const inviteLink = (token: string) => `${window.location.origin}/connect#token=${encodeURIComponent(token)}`;
