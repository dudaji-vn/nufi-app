import { isPlaceholderModel, isChatCapableModel, selectSyncModels } from './models';

describe('isPlaceholderModel', () => {
  it('recognises the LibreChat placeholder that broke a live endpoint', () => {
    expect(isPlaceholderModel('loading...')).toBe(true);
    expect(isPlaceholderModel('Loading...')).toBe(true);
    expect(isPlaceholderModel('  loading...  ')).toBe(true);
  });

  it('leaves real model ids alone', () => {
    expect(isPlaceholderModel('gemini-2.5-flash')).toBe(false);
    expect(isPlaceholderModel('gpt-4o')).toBe(false);
  });
});

describe('isChatCapableModel', () => {
  // Names below are the real ids returned by the provider in production.
  const nonChat = [
    'models/gemini-embedding-001',
    'models/gemini-embedding-2',
    'models/imagen-4.0-generate-001',
    'models/imagen-4.0-ultra-generate-001',
    'models/veo-3.1-generate-preview',
    'models/veo-3.1-lite-generate-preview',
    'models/lyria-3-pro-preview',
    'models/lyria-realtime-exp',
    'models/gemini-2.5-flash-preview-tts',
    'models/gemini-3.1-flash-tts-preview',
    'models/gemini-2.5-flash-native-audio-latest',
    'models/gemini-3.1-flash-live-preview',
    'models/gemini-3.5-live-translate-preview',
    'models/aqa',
    'models/gemini-2.5-computer-use-preview-10-2025',
    'models/deep-research-pro-preview-12-2025',
    'models/antigravity-preview-05-2026',
  ];

  const chat = [
    'models/gemini-2.5-flash',
    'models/gemini-2.5-pro',
    'models/gemini-3-flash-preview',
    'models/gemini-3.1-pro-preview',
    'models/gemini-3.5-flash',
    'models/gemini-flash-latest',
    'models/gemma-4-31b-it',
    'models/nano-banana-pro-preview',
    'models/gemini-3-pro-image',
    'gpt-4o',
  ];

  it.each(nonChat)('rejects non-chat model %s', (model) => {
    expect(isChatCapableModel(model)).toBe(false);
  });

  it.each(chat)('keeps chat-capable model %s', (model) => {
    expect(isChatCapableModel(model)).toBe(true);
  });

  it('matches on the last path segment, not the endpoint namespace', () => {
    // An endpoint literally named "veo" must not disqualify its chat models.
    expect(isChatCapableModel('veo/gemini-2.5-flash')).toBe(true);
  });
});

describe('selectSyncModels', () => {
  it('never registers the placeholder, even when it is the only declared model', () => {
    // Regression: this exact input registered a model named "loading..." in
    // LiteLLM and took a production endpoint down.
    expect(
      selectSyncModels({ declared: ['loading...'], discovered: ['gemini'], fetch: true }),
    ).toEqual(['gemini']);
  });

  it('does not fall back to a placeholder when discovery yields nothing', () => {
    expect(selectSyncModels({ declared: ['loading...'], discovered: [], fetch: true })).toEqual([]);
  });

  it('prefers discovery over declared models when fetch is on', () => {
    expect(
      selectSyncModels({ declared: ['stale-model'], discovered: ['fresh-model'], fetch: true }),
    ).toEqual(['fresh-model']);
  });

  it('falls back to declared models when discovery returns nothing', () => {
    expect(selectSyncModels({ declared: ['gemini'], discovered: [], fetch: true })).toEqual([
      'gemini',
    ]);
  });

  it('ignores discovery entirely when fetch is off', () => {
    expect(
      selectSyncModels({ declared: ['curated'], discovered: ['noise'], fetch: false }),
    ).toEqual(['curated']);
  });

  it('drops non-chat models from a discovered list', () => {
    const discovered = [
      'models/gemini-2.5-flash',
      'models/gemini-embedding-001',
      'models/veo-3.1-generate-preview',
      'models/gemini-2.5-pro',
    ];
    expect(selectSyncModels({ declared: [], discovered, fetch: true })).toEqual([
      'models/gemini-2.5-flash',
      'models/gemini-2.5-pro',
    ]);
  });

  it('deduplicates', () => {
    expect(selectSyncModels({ declared: [], discovered: ['a', 'a', 'b'], fetch: true })).toEqual([
      'a',
      'b',
    ]);
  });
});
