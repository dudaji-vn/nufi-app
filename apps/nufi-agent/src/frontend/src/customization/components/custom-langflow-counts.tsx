// NuFi: upstream renders LangflowCounts here -- a live GitHub star count
// (fetched from api.github.com for langflow-ai/langflow, see
// stores/darkStore.ts) and a Discord member count, both linking off the app
// to upstream's own community channels. This is the override seam upstream
// built for exactly this: a downstream fork swaps behaviour here instead of
// editing appHeaderComponent/index.tsx directly. Rendering nothing removes
// the star badge, the Discord link, and the api.github.com/discord.com
// network calls that back them (see the darkStore refreshStars/
// refreshDiscordCount calls that feed this component -- they're still
// invoked on load elsewhere, but with nothing subscribing to render the
// result, no third-party brand or counter reaches the screen). See
// nufi/README.md "Third-party brand/link sweep" for the rest of the sweep
// this fix came out of.
export function CustomLangflowCounts() {
  return null;
}

export default CustomLangflowCounts;
