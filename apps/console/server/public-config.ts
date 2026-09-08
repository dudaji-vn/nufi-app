export type PublicConfig = { chatUrl: string; litellmUrl: string; worksUrl: string | null };

const strip = (u: string) => u.replace(/\/+$/, '');

/** Runtime public URLs. PUBLIC_* env wins; the Vite build values are the fallback. */
export function readPublicConfig(
  env: Record<string, string | undefined> = process.env,
  fallback: PublicConfig = {
    chatUrl: process.env.VITE_LIBRECHAT_URL ?? 'http://localhost:3080',
    litellmUrl: process.env.VITE_LITELLM_URL ?? 'http://localhost:4000',
    worksUrl: process.env.VITE_WORKS_URL ?? 'https://works.nufi.me',
  },
): PublicConfig {
  const chatUrl = strip(env.PUBLIC_CHAT_URL || fallback.chatUrl);
  const litellmUrl = strip(env.PUBLIC_LITELLM_URL || fallback.litellmUrl);
  const works = env.PUBLIC_WORKS_URL === undefined ? fallback.worksUrl : env.PUBLIC_WORKS_URL;
  return { chatUrl, litellmUrl, worksUrl: works ? strip(works) : null };
}

/** Puts the config on window.__NUFI_PUBLIC__ before any bundle runs. */
export function injectPublicConfig(indexHtml: string, cfg: PublicConfig): string {
  const json = JSON.stringify(cfg).replace(/</g, '\\u003c');
  const tag = `<script>window.__NUFI_PUBLIC__=${json}</script>`;
  return indexHtml.replace('</head>', `${tag}</head>`);
}
