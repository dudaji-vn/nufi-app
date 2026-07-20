/**
 * Model-list hygiene for LiteLLM sync.
 *
 * Two independent problems are handled here, both discovered by syncing a real
 * Google endpoint into LiteLLM:
 *
 * 1. `models.default` is NOT an authoritative list. LibreChat renders it as a
 *    placeholder while `models.fetch` resolves the real list, so it routinely
 *    holds the literal string "loading...". Registering that as a model creates
 *    a deployment that can never serve a request.
 *
 * 2. A provider's `/models` endpoint lists everything it hosts, not just what
 *    can serve `/chat/completions`. Google returns embedding, image, video,
 *    music, TTS and live-audio models there; registering them yields entries
 *    that fail at call time with "not supported for generateContent".
 */

/** Placeholder values LibreChat puts in `models.default`; never real model ids. */
const PLACEHOLDER_MODELS = new Set(['loading...', 'loading', '...']);

/**
 * Model families that a provider lists under `/models` but which cannot serve
 * chat completions. Matched against the last path segment so both bare ids
 * ("veo-3.1-generate-preview") and Google-style ids
 * ("models/veo-3.1-generate-preview") are caught.
 *
 * Deliberately conservative: it targets whole non-chat modalities, not
 * individual models that happen to be broken today. Some chat-shaped models are
 * still rejected upstream for their own reasons (e.g. Google models that only
 * accept the Interactions API); those are left in, because that is a
 * provider-version quirk rather than a modality, and denying them by name would
 * silently drop models the moment the provider fixes them.
 */
const NON_CHAT_PATTERNS: RegExp[] = [
  /embedding/i, // gemini-embedding-001, text-embedding-*
  /^imagen-/i, // image generation
  /^veo-/i, // video generation
  /^lyria/i, // music generation
  /-tts(?:-|$)/i, // text-to-speech variants
  /native-audio/i, // audio-in/audio-out models
  /-live(?:-|$)/i, // realtime/live streaming models
  /^aqa$/i, // attributed question answering
  /computer-use/i, // browser/computer control
  /deep-research/i, // agentic research, Interactions API only
  /antigravity/i, // Interactions API only
];

/** True when the value is a LibreChat UI placeholder rather than a model id. */
export function isPlaceholderModel(model: string): boolean {
  return PLACEHOLDER_MODELS.has(model.trim().toLowerCase());
}

/** True when the model looks able to serve `/chat/completions`. */
export function isChatCapableModel(model: string): boolean {
  const segment = model.split('/').pop() ?? model;
  return !NON_CHAT_PATTERNS.some((re) => re.test(segment));
}

/**
 * Decide which models to register for an endpoint.
 *
 * `fetch !== false` means the provider is the source of truth (LibreChat's own
 * semantics), so discovery wins and `declared` is only a fallback for when
 * discovery yields nothing. Placeholders are always stripped, and non-chat
 * models are dropped from whichever list is used.
 */
export function selectSyncModels(params: {
  declared: string[];
  discovered: string[];
  fetch: boolean;
}): string[] {
  const declared = params.declared.filter((m) => !isPlaceholderModel(m));
  const preferDiscovered = params.fetch && params.discovered.length > 0;
  const chosen = preferDiscovered ? params.discovered : declared;
  return dedupe(chosen.filter((m) => !isPlaceholderModel(m) && isChatCapableModel(m)));
}

function dedupe(models: string[]): string[] {
  return [...new Set(models)];
}
