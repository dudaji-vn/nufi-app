import { describe, expect, test } from 'bun:test';
import { injectPublicConfig, readPublicConfig } from './public-config';

describe('readPublicConfig', () => {
  test('prefers PUBLIC_* env and treats an empty works url as null', () => {
    const cfg = readPublicConfig({
      PUBLIC_CHAT_URL: 'https://nufi.local:3080/',
      PUBLIC_LITELLM_URL: 'https://nufi.local:4000',
      PUBLIC_WORKS_URL: '',
    });
    expect(cfg).toEqual({
      chatUrl: 'https://nufi.local:3080',
      litellmUrl: 'https://nufi.local:4000',
      worksUrl: null,
    });
  });

  test('falls back to the Vite build values when PUBLIC_* are unset', () => {
    const cfg = readPublicConfig(
      {},
      {
        chatUrl: 'http://localhost:3080',
        litellmUrl: 'http://localhost:4000',
        worksUrl: 'https://works.nufi.me',
      },
    );
    expect(cfg.chatUrl).toBe('http://localhost:3080');
    expect(cfg.worksUrl).toBe('https://works.nufi.me');
  });
});

describe('injectPublicConfig', () => {
  test('adds one script before </head> and escapes closing tags', () => {
    const html = '<html><head><title>x</title></head><body></body></html>';
    const out = injectPublicConfig(html, {
      chatUrl: 'https://a:3080',
      litellmUrl: 'https://a:4000',
      worksUrl: '</script><script>alert(1)',
    });
    expect(out).toContain('window.__NUFI_PUBLIC__=');
    expect(out.indexOf('__NUFI_PUBLIC__')).toBeLessThan(out.indexOf('</head>'));
    expect(out).not.toContain('</script><script>alert');
    expect(out).toContain('\\u003c/script>');
  });
});
