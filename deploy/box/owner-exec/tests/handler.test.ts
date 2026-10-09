import { describe, expect, test } from 'bun:test';

import { createApp, type ExecDeps } from '../src/handler';

const CONFIG_YAML =
  'model_list:\n' +
  '  - model_name: qwen2.5-7b\n' +
  '    litellm_params:\n' +
  '      model: openai/qwen2.5:7b\n' +
  '      api_base: http://host.docker.internal:11434/v1\n' +
  '      api_key: os.environ/INFERENCE_API_KEY\n';

function setup(opts: { auditThrows?: boolean; stdout?: string; files?: Record<string, string> } = {}) {
  const spawned: string[][] = [];
  const audits: string[] = [];
  const files: Record<string, string> = { '/config/config.yaml': CONFIG_YAML, ...opts.files };
  const deps: ExecDeps = {
    now: () => new Date('2026-10-05T00:00:00Z'),
    configPath: '/config/config.yaml',
    readFile: (path) => {
      if (!(path in files)) throw new Error(`ENOENT ${path}`);
      return files[path];
    },
    writeFile: (path, data) => {
      files[path] = data;
    },
    auditAppend: (line) => {
      if (opts.auditThrows) throw new Error('disk full');
      audits.push(line);
    },
    spawn: ((o: { cmd: string[] }) => {
      spawned.push(o.cmd);
      return {
        exited: Promise.resolve(0),
        stdout: new Response(opts.stdout ?? 'line1\nline2\n').body,
      };
    }) as unknown as ExecDeps['spawn'],
  };
  const app = createApp(deps);
  const post = (path: string, body: unknown) =>
    app.request(path, { method: 'POST', body: JSON.stringify(body), headers: { 'content-type': 'application/json' } });
  const getJson = (path: string) => app.request(path);
  return { spawned, audits, files, post, getJson };
}

describe('POST /control', () => {
  test('restart caddy spawns the exact argv, audited first', async () => {
    const { spawned, audits, post } = setup();
    const res = await post('/control', { action: 'restart', service: 'caddy' });
    expect(res.status).toBe(200);
    const j = (await res.json()) as { ok: boolean; audit: string };
    expect(j.ok).toBe(true);
    expect(j.audit).toBe(audits[0]);
    expect(spawned).toEqual([['docker', 'compose', '-p', 'nufi-box', 'restart', 'caddy']]);
  });
  test('off-list action or service -> 400, no spawn', async () => {
    const { spawned, post } = setup();
    expect((await post('/control', { action: 'down', service: 'caddy' })).status).toBe(400);
    expect((await post('/control', { action: 'restart', service: 'evil; rm' })).status).toBe(400);
    expect((await post('/control', {})).status).toBe(400);
    expect(spawned).toEqual([]);
  });
  test('audit failure -> no spawn', async () => {
    const { spawned, post } = setup({ auditThrows: true });
    const res = await post('/control', { action: 'stop', service: 'ollama' });
    expect(res.status).toBe(500);
    expect(spawned).toEqual([]);
  });
});

describe('POST /run', () => {
  test('status streams ps output', async () => {
    const { spawned, audits, post } = setup({ stdout: 'a\nb\n' });
    const res = await post('/run', { cmd: 'status' });
    expect(res.status).toBe(200);
    expect(await res.text()).toBe('a\nb\n');
    expect(spawned).toEqual([['docker', 'compose', '-p', 'nufi-box', 'ps']]);
    expect(audits.length).toBe(1);
  });
  test('logs librechat argv', async () => {
    const { spawned, post } = setup();
    await (await post('/run', { cmd: 'logs librechat' })).text();
    expect(spawned[0]).toEqual(['docker', 'compose', '-p', 'nufi-box', 'logs', '--no-color', '--tail=200', 'librechat']);
  });
  test.each(['down', 'logs; rm -rf', 'logs badsvc', ''])('rejects %p', async (cmd) => {
    const { spawned, post } = setup();
    expect((await post('/run', { cmd })).status).toBe(400);
    expect(spawned).toEqual([]);
  });
  test.each(['doctor', 'support'])('%s is informational, no spawn', async (cmd) => {
    const { spawned, post } = setup();
    const res = await post('/run', { cmd });
    expect(res.status).toBe(200);
    expect(await res.text()).toContain(`nufi-box ${cmd}`);
    expect(spawned).toEqual([]);
  });
  test('audit failure -> no spawn', async () => {
    const { spawned, post } = setup({ auditThrows: true });
    expect((await post('/run', { cmd: 'status' })).status).toBe(500);
    expect(spawned).toEqual([]);
  });
});

describe('POST /control whole box', () => {
  test('missing/null service -> 400, no spawn (never whole-box by default)', async () => {
    const { spawned, post } = setup();
    expect((await post('/control', { action: 'restart' })).status).toBe(400);
    expect((await post('/control', { action: 'restart', service: null })).status).toBe(400);
    expect(spawned).toEqual([]);
  });
  test('explicit __box__ restart -> box argv, audited', async () => {
    const { spawned, audits, post } = setup();
    expect((await post('/control', { action: 'restart', service: '__box__' })).status).toBe(200);
    expect(spawned).toEqual([['docker', 'compose', '-p', 'nufi-box', 'restart']]);
    expect(audits[0]).toContain('__box__');
  });
  test('service __box__ -> box argv', async () => {
    const { spawned, post } = setup();
    await post('/control', { action: 'stop', service: '__box__' });
    expect(spawned).toEqual([['docker', 'compose', '-p', 'nufi-box', 'stop']]);
  });
  test('invalid action -> 400, no spawn', async () => {
    const { spawned, post } = setup();
    expect((await post('/control', { action: 'down' })).status).toBe(400);
    expect(spawned).toEqual([]);
  });
});

describe('GET /config and POST /reconfigure', () => {
  test('GET /config reads the model + base from litellm/config.yaml', async () => {
    const { getJson } = setup();
    const res = await getJson('/config');
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ aiModel: 'qwen2.5:7b', aiBaseUrl: 'http://host.docker.internal:11434/v1' });
  });

  test('POST /reconfigure rewrites the config, audits, and re-creates litellm-proxy', async () => {
    const { spawned, audits, files, post } = setup();
    const res = await post('/reconfigure', { aiBaseUrl: 'http://10.0.0.9:8000/v1', aiModel: 'llama-3-70b-instruct' });
    expect(res.status).toBe(200);
    const j = (await res.json()) as { ok: boolean; audit: string };
    expect(j.ok).toBe(true);
    expect(j.audit).toBe(audits[0]);
    const out = files['/config/config.yaml'];
    expect(out).toContain('model: openai/llama-3-70b-instruct');
    expect(out).toContain('api_base: http://10.0.0.9:8000/v1');
    expect(out).toContain('api_key: os.environ/INFERENCE_API_KEY'); // untouched
    expect(out).toContain('model_name: qwen2.5-7b'); // alias untouched
    expect(spawned).toEqual([['docker', 'compose', '-p', 'nufi-box', 'restart', 'litellm-proxy']]);
  });

  test('a non-http base URL is 400 — no write, no spawn', async () => {
    const { spawned, files, post } = setup();
    const before = files['/config/config.yaml'];
    expect((await post('/reconfigure', { aiBaseUrl: 'ftp://x', aiModel: 'm' })).status).toBe(400);
    expect(files['/config/config.yaml']).toBe(before);
    expect(spawned).toEqual([]);
  });

  test('.env is never read or written', async () => {
    const { files, post } = setup();
    await post('/reconfigure', { aiBaseUrl: 'http://10.0.0.9:8000/v1', aiModel: 'm' });
    expect(Object.keys(files).some((p) => p.endsWith('/.env'))).toBe(false);
  });
});
