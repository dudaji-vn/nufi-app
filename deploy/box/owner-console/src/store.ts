import { randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';

export type UserRecord = {
  id: string;
  name: string;
  os: 'macos' | 'windows' | 'linux';
  keyId: string;
  token: string;
  createdAt: string;
  // How the owner hands the join to the member: a downloadable join file
  // ('public') or a LAN-only link ('private', the default). Optional so users
  // created before this field default to 'private' (the link).
  addingMethod?: 'public' | 'private';
};

const file = () => join(process.env.NUFI_STATE_DIR || '/state', 'users.json');

async function read(): Promise<UserRecord[]> {
  try {
    return JSON.parse(await readFile(file(), 'utf8')) as UserRecord[];
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === 'ENOENT') return [];
    throw e;
  }
}

async function write(users: UserRecord[]): Promise<void> {
  const path = file();
  await mkdir(dirname(path), { recursive: true });
  const tmp = `${path}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(tmp, JSON.stringify(users, null, 2), { mode: 0o600 });
  await rename(tmp, path);
}

// Serializes every read-modify-write so concurrent mutations never drop records.
let queue: Promise<unknown> = Promise.resolve();
function mutate<T>(fn: (users: UserRecord[]) => T): Promise<T> {
  const run = queue.then(async () => {
    const users = await read();
    const out = fn(users);
    await write(users);
    return out;
  });
  queue = run.catch(() => undefined); // a failure must not poison later mutations
  return run;
}

export async function listUsers(): Promise<UserRecord[]> {
  await queue;
  return read();
}

export function addUser(u: Omit<UserRecord, 'id' | 'createdAt'>): Promise<UserRecord> {
  return mutate((users) => {
    const rec: UserRecord = { ...u, id: randomUUID(), createdAt: new Date().toISOString() };
    users.push(rec);
    return rec;
  });
}

export function updateUser(id: string, patch: Partial<UserRecord>): Promise<UserRecord> {
  return mutate((users) => {
    const i = users.findIndex((x) => x.id === id);
    if (i < 0) throw new Error(`user not found: ${id}`);
    users[i] = { ...users[i], ...patch, id };
    return users[i];
  });
}

export function removeUser(id: string): Promise<void> {
  return mutate((users) => {
    const i = users.findIndex((x) => x.id === id);
    if (i >= 0) users.splice(i, 1);
  });
}
