# Lane 5 (Using the app) run log — 2026-09-07

Branch `docs/audit-end-user` from origin/main 381fe8731 (after lane 6
merged).

The app's labels and behaviour were checked against `apps/chat/client/src`
(`locales/en/translation.json` for every quoted string, `store/settings.ts`
for defaults, `hooks/Nav/useSideNavLinks.ts`, `components/Chat/Header.tsx`,
`components/Chat/Input/BadgeRow.tsx` and `ToolsDropdown.tsx`,
`components/Chat/Messages/Fork.tsx`, `components/Nav/Settings.tsx` and
`SettingsTabs/*` for what Basic mode hides and what each tab holds,
`components/Chat/Input/Files/AttachFileMenu.tsx` for the attach options,
`components/Chat/Messages/Content/EditMessage.tsx` for Save & Submit) and
the console against `apps/console/src` (`components/key-table.tsx`,
`key-generate-modal.tsx`, `key-reveal-once-modal.tsx`, `routes/index.tsx`,
`lib/format.ts`). `git log nufi-v0.1.12..origin/main -- apps/chat/client`
is empty, so the client in production is the client on `main`.

What the hosted deployment enables was read from the unauthenticated
startup config at `https://chat.nufi.me/api/config` (2026-09-07):
registration open, Google sign-in on, email off (so no password reset),
shared links on for signed-in members only, account deletion allowed,
title "Nufi Chat", Help & FAQ pointing at `librechat.ai`. The agents
capabilities in production are governed by the admin panel's stored
configuration, not by `deploy/railway/librechat.yaml`; the existing
screenshots, taken on `chat.nufi.me`, show the Tools menu with File
Search, Web Search, Skills, Run Code and Artifacts, and no image tool.

No signed-in session: the shared test account's password was not
available, so no screenshot was recaptured and nothing that needs a
session (the model list, whether web search actually returns results,
the Skills panel) was exercised live.

## Checked

| # | Claim | Result |
|---|---|---|
| 1 | default interface | **Basic** (`store/settings.ts:79`); hides Agent Builder, Skills, Prompts, Memories, Bookmarks, Teams, Parameters, MCP, Presets, multi-conversation, Fork, the Tools menu, and the Chat and Commands settings tabs. No page mentioned it. New page `advanced-mode.mdx`; every affected page now says so |
| 2 | switch location | avatar menu **Advanced**/**Basic** (`AccountSettings.tsx:127-134`); **Settings → General → Interface**; remembered per browser (localStorage) |
| 3 | intro banner | "Basic interface enabled — switch to Advanced anytime in Settings." (`translation.json:1244`) |
| 4 | Tools menu | rendered only in Advanced and only with ephemeral badges, i.e. an agent (`BadgeRow.tsx:333`) |
| 5 | sign-up, Google | registration open and Google enabled on the hosted app (`/api/config`) |
| 6 | password reset | `passwordResetEnabled: false`, `emailEnabled: false` → no link on the sign-in screen (**F27**) |
| 7 | 2FA | button **Enable 2FA**; Account tab shows it for password (`local`) accounts only (`SettingsTabs/Account/Account.tsx:22`) |
| 8 | account menu | My Files, Help & FAQ, Console, Agents, Advanced/Basic, Settings, Log out; the old `chat-account-menu.png` predates Agents and the mode switch, replaced by `chat-agents-menu.png` |
| 9 | Settings tabs | General, Chat + Commands (Advanced), Speech, Data controls, Account; Balance only if enabled (`Settings.tsx:41-47`); Data controls = Import conversations, Shared links, Revoke Keys, Delete TTS cache, Clear all chats |
| 10 | log out scope | current session only (`api/server/services/AuthService.js:72-90`); the docs said "everywhere" |
| 11 | reply toolbar | Speaker, Copy, Edit, Fork (Advanced), thumbs, Regenerate, Continue (`HoverButtons.tsx`); the old page said "Branch" and omitted Continue |
| 12 | edit flow | **Save & Submit** re-asks and branches; **Save** edits in place (`EditMessage.tsx:190,203`) |
| 13 | bookmarks | a tag from the header bookmark menu, Advanced only; no star (`Chat/Menus/BookmarkMenu.tsx`) |
| 14 | `Ctrl/⌘ + K` jump bar | does not exist; no handler in the client. Removed |
| 15 | rate-limit text | "Too many requests. Try again later" (`forkLimiters.js:51`); "please slow down" and "Budget reached" were invented |
| 16 | share a conversation | header **Share** → Create link → Copy link; `sharedLinksEnabled: true`, `publicSharedLinksEnabled: false` |
| 17 | conversation menu | Rename, Duplicate, Archive, Delete (`ConvoOptions.tsx`); Archived chats under Settings → General |
| 18 | attach menu | Upload to Provider, Upload Image, Upload as Text (needs `context`), Upload for File Search, Upload to Code Environment (needs `execute_code`) (`AttachFileMenu.tsx:170-225`) |
| 19 | file types and limits | png, jpeg, webp, gif, pdf, txt, md, csv, docx, json; 5 files / 20 MB / 50 MB on the `Nufi` endpoint (`deploy/railway/librechat.yaml:67-83`); no code files |
| 20 | image generation | not offered on the hosted app; `/image` does not exist. Guide removed, redirect added |
| 21 | deleting a conversation | does not delete its files (`data-schemas/src/methods/conversation.ts:484-508`) |
| 22 | speech defaults | STT and TTS on with the **browser** engine (`store/settings.ts:59-67`); Conversation Mode, Engine, Voice, Language, Audio Playback Rate on the Speech tab |
| 23 | console | tabs Profile / Usage / API keys; columns Name, Usage, Limits, Created, Expires; **Generate Key**; **Alias** required; defaults $10/30d, 10,000 TPM, 60 RPM, 90d; reveal modal with snippets and **I've saved it**; mask first 3 + last 4; trash icon → Revoke; last 50 requests |
| 24 | gateway URL and model | `https://api.codechi.me/v1` and the `gemini` alias; `api.nufi.me` and `qwen2.5-7b` never existed |
| 25 | guardrail refusal | the styled card is the agents path (`controllers/agents/client.js:1094`); on a plain model it is an error with the same `grd_` reference; the two-detector rule applies to user and assistant text, one detector suffices for tool/web text (`entrypoints.py:917-929`) |
| 26 | team invitations | in-app; the app also says "An email may be sent if email is configured", and it is not |

## Not executed

Recapturing the 20 screenshots (`bun run screenshots` with the test
account), confirming the curated model list a Basic-mode account sees on
`chat.nufi.me`, and a live web-search or Run Code result. All need the
shared test account.
