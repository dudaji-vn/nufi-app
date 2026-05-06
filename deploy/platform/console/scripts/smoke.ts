#!/usr/bin/env bun
/**
 * console smoke test — drives the full W3 happy path against a running
 * stack. Exits non-zero if any step fails. Intended for local regression
 * checks and (eventually) CI.
 *
 * Reads E2E_USER_EMAIL / E2E_USER_PASSWORD / E2E_MODEL from the env
 * (loaded from the repo-root .env by the bash wrapper).
 */

const LIBRECHAT = process.env.LIBRECHAT_URL ?? 'http://localhost:3080';
const CONSOLE = process.env.CONSOLE_URL ?? 'http://localhost:3001';
const LITELLM = process.env.LITELLM_URL ?? 'http://localhost:4000';

const EMAIL = required('E2E_USER_EMAIL');
const PASSWORD = required('E2E_USER_PASSWORD');
const NAME = process.env.E2E_USER_NAME ?? 'Smoke Test Bot';
const MODEL = process.env.E2E_MODEL ?? 'qwen2.5-3b';

// LibreChat 0.7.5's uaParser middleware rejects non-browser User-Agents.
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0';

const C = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  gray: '\x1b[90m',
  yellow: '\x1b[33m',
  bold: '\x1b[1m',
  reset: '\x1b[0m',
};

function required(name: string): string {
  const v = process.env[name];
  if (!v) {
    console.error(`${C.red}Missing required env: ${name}${C.reset}`);
    process.exit(2);
  }
  return v;
}

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

async function postJson(url: string, body: unknown, init: RequestInit = {}): Promise<Response> {
  return fetch(url, {
    method: 'POST',
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    body: JSON.stringify(body),
  });
}

async function loginOrRegister(): Promise<string> {
  const headers = { 'User-Agent': UA };

  const login = await postJson(
    `${LIBRECHAT}/api/auth/login`,
    { email: EMAIL, password: PASSWORD },
    { headers },
  );
  if (login.ok) {
    const body = (await login.json()) as { token: string };
    if (!body.token) throw new Error('login response missing token');
    return body.token;
  }
  if (login.status !== 401 && login.status !== 422) {
    throw new Error(`login failed: ${login.status} ${await login.text()}`);
  }

  // 401/422 → user might not exist yet. Try registering.
  const reg = await postJson(
    `${LIBRECHAT}/api/auth/register`,
    {
      email: EMAIL,
      password: PASSWORD,
      confirm_password: PASSWORD,
      name: NAME,
      username: NAME,
    },
    { headers },
  );
  if (!reg.ok) throw new Error(`register failed: ${reg.status} ${await reg.text()}`);

  const login2 = await postJson(
    `${LIBRECHAT}/api/auth/login`,
    { email: EMAIL, password: PASSWORD },
    { headers },
  );
  if (!login2.ok)
    throw new Error(`login after register failed: ${login2.status} ${await login2.text()}`);
  const body = (await login2.json()) as { token: string };
  return body.token;
}

async function rpc(path: string, input: unknown, bearer: string): Promise<Response> {
  return postJson(`${CONSOLE}/rpc${path}`, input, {
    headers: { Authorization: `Bearer ${bearer}` },
  });
}

async function rpcOk<T>(path: string, input: unknown, bearer: string): Promise<T> {
  const res = await rpc(path, input, bearer);
  const text = await res.text();
  if (!res.ok) throw new Error(`${path} → ${res.status}: ${text.slice(0, 300)}`);
  const parsed = text ? JSON.parse(text) : {};
  return (parsed.json ?? parsed) as T;
}

let passed = 0;
let failed = 0;

async function step(name: string, fn: () => Promise<void>): Promise<void> {
  process.stdout.write(`  ${C.gray}→${C.reset} ${name}…`);
  const start = Date.now();
  try {
    await fn();
    const dt = Date.now() - start;
    process.stdout.write(`\r  ${C.green}✓${C.reset} ${name} ${C.gray}(${dt} ms)${C.reset}\n`);
    passed++;
  } catch (err) {
    process.stdout.write(`\r  ${C.red}✗${C.reset} ${name}\n`);
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`    ${C.red}${msg}${C.reset}`);
    failed++;
  }
}

console.log(`\n${C.bold}NPUOps Console — smoke test${C.reset}`);
console.log(`  Console:   ${CONSOLE}`);
console.log(`  LibreChat: ${LIBRECHAT}`);
console.log(`  LiteLLM:   ${LITELLM}`);
console.log(`  Model:     ${MODEL}\n`);

// Authenticate first — every subsequent step depends on the bearer.
let bearer: string;
process.stdout.write(`  ${C.gray}→${C.reset} Authenticating against LibreChat…`);
try {
  bearer = await loginOrRegister();
  process.stdout.write(`\r  ${C.green}✓${C.reset} Authenticated against LibreChat\n`);
} catch (err) {
  const msg = err instanceof Error ? err.message : String(err);
  process.stdout.write(`\r  ${C.red}✗${C.reset} Authentication failed\n`);
  console.error(`    ${C.red}${msg}${C.reset}\n`);
  process.exit(1);
}

let createdKey = '';
let createdToken = '';

await step('GET /_health returns ok', async () => {
  const res = await fetch(`${CONSOLE}/_health`);
  assert(res.ok, `expected 200, got ${res.status}`);
  const body = (await res.json()) as { ok: boolean };
  assert(body.ok === true, 'body.ok must be true');
});

await step('rpc/me/get without auth returns 401', async () => {
  const res = await postJson(`${CONSOLE}/rpc/me/get`, {});
  assert(res.status === 401, `expected 401, got ${res.status}`);
});

await step('rpc/me/get with auth returns user info (JIT-provisioned)', async () => {
  type Me = { id: string; role: string; spend: { total: number } };
  const me = await rpcOk<Me>('/me/get', {}, bearer);
  assert(me.id, 'expected me.id');
  assert(me.role === 'USER' || me.role === 'ADMIN', `unexpected role: ${me.role}`);
  assert(typeof me.spend.total === 'number', 'expected spend.total to be a number');
});

await step('rpc/keys/create returns full sk-… key once', async () => {
  type CreateResult = { key: string; view: { token: string; alias: string | null } };
  const alias = `smoke-${Date.now()}`;
  const result = await rpcOk<CreateResult>(
    '/keys/create',
    {
      json: {
        alias,
        maxBudget: 1,
        budgetDuration: '24h',
        tpmLimit: 10_000,
        rpmLimit: 5,
        duration: '7d',
      },
    },
    bearer,
  );
  assert(typeof result.key === 'string' && result.key.startsWith('sk-'), 'expected sk-… key');
  assert(result.view.alias === alias, `expected view.alias=${alias}`);
  createdKey = result.key;
  createdToken = result.view.token;
});

await step('issued key works against LiteLLM /v1/chat/completions', async () => {
  const res = await postJson(
    `${LITELLM}/v1/chat/completions`,
    {
      model: MODEL,
      messages: [{ role: 'user', content: 'pong' }],
      max_tokens: 5,
    },
    { headers: { Authorization: `Bearer ${createdKey}` } },
  );
  // Read body once — fetch streams can only be consumed a single time.
  const text = await res.text();
  assert(res.ok, `expected 200, got ${res.status}: ${text.slice(0, 200)}`);
  const body = JSON.parse(text) as { choices?: Array<{ message?: { content?: string } }> };
  assert(body.choices?.[0]?.message?.content, 'expected response content');
});

await step('rpc/keys/list shows the new key', async () => {
  type Key = { token: string; alias: string | null };
  const list = await rpcOk<Key[]>('/keys/list', {}, bearer);
  assert(Array.isArray(list), 'expected an array');
  assert(
    list.some((k) => k.token === createdToken),
    'expected new key in list',
  );
});

await step('hammering past rpm_limit produces a 429', async () => {
  const fanout = 20; // rpm_limit=5; 20 in parallel guarantees a 429
  const responses = await Promise.all(
    Array.from({ length: fanout }, () =>
      postJson(
        `${LITELLM}/v1/chat/completions`,
        {
          model: MODEL,
          messages: [{ role: 'user', content: 'x' }],
          max_tokens: 1,
        },
        { headers: { Authorization: `Bearer ${createdKey}` } },
      ),
    ),
  );
  const codes = responses.map((r) => r.status);
  assert(codes.includes(429), `expected a 429, got [${codes.join(', ')}]`);
});

await step('rpc/keys/remove revokes the key', async () => {
  const result = await rpcOk<{ ok: true }>(
    '/keys/remove',
    {
      json: { token: createdToken },
    },
    bearer,
  );
  assert(result.ok === true, 'expected ok:true');
});

await step('revoked key is rejected by LiteLLM', async () => {
  // LiteLLM's deletion is sometimes eventually-consistent against its in-memory
  // cache. Retry briefly so the assertion is stable.
  let lastStatus = 0;
  for (let i = 0; i < 8; i++) {
    const res = await postJson(
      `${LITELLM}/v1/chat/completions`,
      {
        model: MODEL,
        messages: [{ role: 'user', content: 'x' }],
        max_tokens: 1,
      },
      { headers: { Authorization: `Bearer ${createdKey}` } },
    );
    lastStatus = res.status;
    if (res.status === 401) return;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`expected 401 after revoke, last seen ${lastStatus}`);
});

await step('rpc/usage/daily returns a stable 7-day series', async () => {
  type Daily = {
    days: number;
    total: number;
    series: Array<{ date: string; spend: number }>;
    requests: number;
  };
  const daily = await rpcOk<Daily>('/usage/daily', { json: { days: 7 } }, bearer);
  assert(daily.days === 7, `expected days=7, got ${daily.days}`);
  assert(daily.series.length === 7, `expected 7 series points, got ${daily.series.length}`);
  assert(typeof daily.total === 'number', 'expected total to be a number');
  assert(
    daily.requests > 0,
    `expected requests>0 (smoke test ran chat traffic), got ${daily.requests}`,
  );
});

await step('rpc/usage/byModel collapses provider prefix', async () => {
  type ByModel = { breakdown: Array<{ model: string; spend: number; requests: number }> };
  const r = await rpcOk<ByModel>('/usage/byModel', { json: { days: 30 } }, bearer);
  assert(r.breakdown.length > 0, 'expected at least one model in the breakdown');
  assert(
    !r.breakdown.some((b) => b.model.startsWith('openai/')),
    `unexpected openai/ prefix in breakdown: ${r.breakdown.map((b) => b.model).join(', ')}`,
  );
});

await step('rpc/usage/recent returns rows newest-first', async () => {
  type Recent = {
    rows: Array<{ startTime: string; model: string | null; via: 'chat' | 'key' }>;
  };
  const r = await rpcOk<Recent>('/usage/recent', { json: { limit: 10 } }, bearer);
  assert(r.rows.length > 0, 'expected at least one recent row');
  for (let i = 1; i < r.rows.length; i++) {
    assert(
      r.rows[i - 1].startTime >= r.rows[i].startTime,
      `rows not sorted desc at index ${i}: ${r.rows[i - 1].startTime} < ${r.rows[i].startTime}`,
    );
  }
});

await step('rpc/usage/summary returns joined LiteLLM + Langfuse stats', async () => {
  type Summary = {
    days: number;
    totalSpend: number;
    totalRequests: number;
    modelsUsed: number;
    primaryHardware: { hardwareId: string; backendType: string | null } | null;
  };
  const r = await rpcOk<Summary>('/usage/summary', { json: { days: 7 } }, bearer);
  assert(r.days === 7, `expected days=7, got ${r.days}`);
  assert(r.totalRequests > 0, `expected requests>0, got ${r.totalRequests}`);
  assert(r.modelsUsed > 0, `expected modelsUsed>0, got ${r.modelsUsed}`);
  // primaryHardware should be set after the W2.5 hook is in place; the
  // procedure deliberately ignores the `unknown` bucket so freshly hooked
  // stacks don't show "primary hardware: unknown".
  assert(r.primaryHardware, 'expected primaryHardware to be populated');
  assert(
    r.primaryHardware.hardwareId === 'mac-local',
    `expected primaryHardware=mac-local, got ${r.primaryHardware.hardwareId}`,
  );
});

await step('rpc/usage/byHardware aggregates Langfuse traces by hardware_id', async () => {
  type ByHardware = {
    breakdown: Array<{
      hardwareId: string;
      backendType: string | null;
      spend: number;
      requests: number;
    }>;
    truncated: boolean;
  };
  const r = await rpcOk<ByHardware>('/usage/byHardware', { json: { days: 7 } }, bearer);
  assert(r.breakdown.length > 0, 'expected at least one hardware bucket');
  // Every bucket should be from the W2.5 callback, so backendType is set
  // and hardwareId is not the 'unknown' fallback.
  const macLocal = r.breakdown.find((b) => b.hardwareId === 'mac-local');
  assert(
    macLocal,
    `expected mac-local in breakdown, got ${r.breakdown.map((b) => b.hardwareId).join(', ')}`,
  );
  assert(macLocal.backendType === 'gpu', `expected backendType=gpu, got ${macLocal.backendType}`);
  assert(macLocal.requests > 0, 'expected requests>0 for mac-local');
});

console.log(
  `\n${C.bold}Result:${C.reset} ${C.green}${passed} passed${C.reset} · ` +
    `${failed === 0 ? C.gray : C.red}${failed} failed${C.reset}\n`,
);
process.exit(failed === 0 ? 0 : 1);
