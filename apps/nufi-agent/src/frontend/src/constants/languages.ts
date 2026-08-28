export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English" },
  // Korean sits second by request of the Korean team, who are the largest
  // non-English group using this instance. The rest keep upstream's order.
  { code: "ko", label: "한국어" },
  { code: "fr", label: "Français" },
  { code: "es", label: "Español" },
  { code: "de", label: "Deutsch" },
  { code: "pt", label: "Português" },
  { code: "ja", label: "日本語" },
  { code: "zh-Hans", label: "中文" },
] as const;
