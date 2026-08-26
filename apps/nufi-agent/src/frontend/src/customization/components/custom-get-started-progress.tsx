import type { Users } from "@/types/api";

// NuFi: upstream's GetStartedProgress is a sidebar onboarding checklist with
// two of its three steps -- "Star Repo" and "Join Community" -- linking
// straight out to langflow-ai/langflow's own GitHub repo and Discord
// (GITHUB_URL/DISCORD_URL in get-started-progress.tsx), shown to every
// signed-in user with a fresh project until dismissed. Same third-party
// brand/link exposure as the header's star-count widget
// (custom-langflow-counts.tsx), just as a call-to-action instead of a
// passive badge -- arguably worse, since it actively invites the click.
// Rendering nothing drops the whole checklist rather than forking its
// percentage/step logic to keep only the (legitimate) "create a flow" step:
// every other entry point already offers "create a flow" (the empty-page
// button, the main-page header, etc. -- see empty-page.tsx), so nothing is
// lost by removing this one. Known side effect: header-buttons.tsx (core,
// not a customization override, not edited here) renders a <hr> divider
// unconditionally alongside this component when it would have shown, so a
// stray divider line can appear with nothing above it. Cosmetic only --
// judged cheaper than forking the checklist or editing another core file.
// See nufi/README.md "Third-party brand/link sweep".
export function CustomGetStartedProgress(_props: {
  userData: Users;
  isGithubStarred: boolean;
  isDiscordJoined: boolean;
  handleDismissDialog: () => void;
}) {
  return null;
}

export default CustomGetStartedProgress;
