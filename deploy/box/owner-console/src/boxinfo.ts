// The box facts the dashboard shows, read from the environment the compose
// service injects. Deliberately only non-secret facts: the console never sees
// the box's secrets (JWT, DB passwords, gateway keys). Mesh status is whatever
// the box's .env held when this container last started; `nufi-box mesh up|down`
// re-creates the console so a join/leave is reflected.

export type Mesh = {
  serverUrl: string;
  selfHost: boolean;
  joined: boolean;
  ip: string;
  host: string;
};

export type BoxInfo = {
  name: string;
  host: string;
  ip: string;
  departments: string[];
  mesh: Mesh;
};

export function boxInfo(env: Record<string, string | undefined> = process.env): BoxInfo {
  const ip = env.BOX_MESH_IP ?? '';
  const host = env.BOX_MESH_HOST ?? '';
  return {
    name: env.BOX_NAME ?? '',
    host: env.BOX_HOST ?? '',
    ip: env.BOX_IP ?? '',
    departments: (env.DEPARTMENTS ?? '')
      .split(',')
      .map((d) => d.trim())
      .filter(Boolean),
    mesh: {
      serverUrl: env.MESH_SERVER_URL ?? '',
      selfHost: env.NUFI_SELF_HOST_COORD === '1',
      joined: Boolean(ip),
      ip,
      host,
    },
  };
}
