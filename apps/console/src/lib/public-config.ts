export type PublicConfig = { chatUrl: string; litellmUrl: string; worksUrl: string | null };

declare global {
  interface Window {
    __NUFI_PUBLIC__?: Partial<PublicConfig>;
  }
}

export function publicConfig(): PublicConfig {
  const w = typeof window !== 'undefined' ? (window.__NUFI_PUBLIC__ ?? {}) : {};
  return {
    chatUrl: w.chatUrl ?? import.meta.env.VITE_LIBRECHAT_URL ?? 'http://localhost:3080',
    litellmUrl: w.litellmUrl ?? import.meta.env.VITE_LITELLM_URL ?? 'http://localhost:4000',
    worksUrl:
      w.worksUrl === undefined
        ? (import.meta.env.VITE_WORKS_URL ?? 'https://works.nufi.me')
        : w.worksUrl,
  };
}
