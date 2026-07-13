import {
  normalizeBaseURL,
  getLiteLLMConfig,
  createLiteLLMClient,
  LiteLLMError,
} from './client';

const MASTER = 'sk-master-secret-value';

describe('normalizeBaseURL', () => {
  it('strips trailing slash and /v1', () => {
    expect(normalizeBaseURL('https://api.codechi.me/')).toBe('https://api.codechi.me');
    expect(normalizeBaseURL('https://api.codechi.me/v1')).toBe('https://api.codechi.me');
    expect(normalizeBaseURL('https://api.codechi.me/v1/')).toBe('https://api.codechi.me');
    expect(normalizeBaseURL('https://api.codechi.me')).toBe('https://api.codechi.me');
  });
});

describe('getLiteLLMConfig', () => {
  const OLD = { ...process.env };
  afterEach(() => {
    process.env = { ...OLD };
  });

  it('returns null when the feature flag is off', () => {
    process.env.LITELLM_SYNC_ENABLED = 'false';
    process.env.LITELLM_BASE_URL = 'https://api.codechi.me';
    process.env.LITELLM_MASTER_KEY = MASTER;
    expect(getLiteLLMConfig()).toBeNull();
  });

  it('returns null when base URL or key missing even if enabled', () => {
    process.env.LITELLM_SYNC_ENABLED = 'true';
    process.env.LITELLM_BASE_URL = '';
    process.env.LITELLM_MASTER_KEY = MASTER;
    expect(getLiteLLMConfig()).toBeNull();
  });

  it('returns a normalized config when fully enabled', () => {
    process.env.LITELLM_SYNC_ENABLED = 'true';
    process.env.LITELLM_BASE_URL = 'https://api.codechi.me/v1/';
    process.env.LITELLM_MASTER_KEY = MASTER;
    expect(getLiteLLMConfig()).toEqual({
      enabled: true,
      baseURL: 'https://api.codechi.me',
      masterKey: MASTER,
    });
  });
});

describe('createLiteLLMClient', () => {
  const cfg = { enabled: true, baseURL: 'https://api.codechi.me', masterKey: MASTER };
  const originalFetch = global.fetch;
  const mockFetch = jest.fn() as unknown as jest.MockedFunction<typeof fetch>;

  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = mockFetch;
  });
  afterAll(() => {
    global.fetch = originalFetch;
  });

  const ok = (body: unknown) =>
    ({ ok: true, status: 200, text: async () => JSON.stringify(body) }) as Response;

  it('modelNew posts to /model/new with an OpenAI-compatible body and parses model_info.id', async () => {
    mockFetch.mockResolvedValueOnce(ok({ model_info: { id: 'mid-123' } }));
    const client = createLiteLLMClient(cfg);
    const res = await client.modelNew({
      modelName: 'OpenAI/gpt-4o',
      providerModel: 'openai/gpt-4o',
      apiBase: 'https://api.openai.com/v1',
      apiKey: 'sk-real',
    });
    expect(res.modelId).toBe('mid-123');
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe('https://api.codechi.me/model/new');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({
      model_name: 'OpenAI/gpt-4o',
      litellm_params: {
        model: 'openai/gpt-4o',
        api_base: 'https://api.openai.com/v1',
        api_key: 'sk-real',
      },
    });
    expect((init?.headers as Record<string, string>).Authorization).toBe(`Bearer ${MASTER}`);
  });

  it('modelNew falls back to /model/info when the create response omits an id', async () => {
    mockFetch
      .mockResolvedValueOnce(ok({})) // /model/new — no id
      .mockResolvedValueOnce(
        ok({ data: [{ model_name: 'OpenAI/gpt-4o', model_info: { id: 'mid-from-info' } }] }),
      );
    const client = createLiteLLMClient(cfg);
    const res = await client.modelNew({
      modelName: 'OpenAI/gpt-4o',
      providerModel: 'openai/gpt-4o',
      apiBase: 'https://api.openai.com/v1',
      apiKey: 'sk-real',
    });
    expect(res.modelId).toBe('mid-from-info');
    expect((mockFetch.mock.calls[1][0] as string)).toBe('https://api.codechi.me/model/info');
  });

  it('keyGenerate returns the minted key', async () => {
    mockFetch.mockResolvedValueOnce(ok({ key: 'sk-virtual-xyz' }));
    const client = createLiteLLMClient(cfg);
    const res = await client.keyGenerate({
      models: ['OpenAI/gpt-4o'],
      keyAlias: 'nufi-ep-openai',
      metadata: { endpoint: 'OpenAI' },
    });
    expect(res.key).toBe('sk-virtual-xyz');
  });

  it('throws LiteLLMError on non-2xx and never includes the master key in the error', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: async () => 'internal error',
    } as Response);
    const client = createLiteLLMClient(cfg);
    let caught: unknown;
    try {
      await client.modelDelete('mid-123');
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(LiteLLMError);
    expect((caught as LiteLLMError).status).toBe(500);
    const serialized = JSON.stringify({
      msg: (caught as LiteLLMError).message,
      body: (caught as LiteLLMError).body,
    });
    expect(serialized).not.toContain(MASTER);
  });
});
