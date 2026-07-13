import {
  litellmModelName,
  providerModel,
  credFingerprint,
  keyAlias,
  SENTINEL_VIRTUAL_KEY,
} from './naming';

describe('naming', () => {
  it('namespaces model names by endpoint', () => {
    expect(litellmModelName('OpenAI', 'gpt-4o')).toBe('OpenAI/gpt-4o');
    expect(litellmModelName('Azure', 'gpt-4o')).toBe('Azure/gpt-4o');
  });

  it('prefixes provider model with openai/', () => {
    expect(providerModel('gpt-4o')).toBe('openai/gpt-4o');
  });

  it('credFingerprint is stable and changes with baseURL or apiKey', () => {
    const a = credFingerprint('https://x/v1', 'sk-1');
    expect(a).toBe(credFingerprint('https://x/v1', 'sk-1'));
    expect(a).not.toBe(credFingerprint('https://y/v1', 'sk-1'));
    expect(a).not.toBe(credFingerprint('https://x/v1', 'sk-2'));
    expect(a).toMatch(/^[a-f0-9]{64}$/);
  });

  it('keyAlias slugifies the endpoint name', () => {
    expect(keyAlias('OpenAI Prod!')).toBe('nufi-ep-openai-prod');
    expect(keyAlias('')).toBe('nufi-ep-endpoint');
  });

  it('sentinel key is a non-empty invalid-looking key', () => {
    expect(SENTINEL_VIRTUAL_KEY).toMatch(/^sk-/);
  });
});
