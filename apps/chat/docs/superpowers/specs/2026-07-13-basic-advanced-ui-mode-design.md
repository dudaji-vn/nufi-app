# Basic / Advanced UI Mode — Design

**Date:** 2026-07-13
**Status:** Approved for planning
**Owner:** NUFI fork (LibreChat)

## 1. Summary

Introduce a per-user **UI Mode** with two levels — **Basic** (default) and **Advanced** — so
general end-customers get a simple, ChatGPT-like "type → get an answer" experience, while
power users can opt into the full feature surface. The mode is a client-side preference that
**hides complexity for clarity**; it never grants access to anything the user's role does not
already permit.

Vietnamese one-line: *Chế độ giao diện Cơ bản/Nâng cao theo từng user, mặc định Cơ bản, user tự
bật Nâng cao trong Cài đặt. Chỉ ẩn cho gọn, không cấp thêm quyền.*

## 2. Motivation

Product feedback: overall reception is positive, but **normal end-customers find the app hard to
understand — too many buttons, tools, and parameters**. The target audience expects a simple
chat experience. We need to reduce cognitive load by default without removing power features for
users who want them.

## 3. Goals & Non-Goals

### Goals
- New and existing users start in **Basic**; Basic looks and feels like a clean chat app.
- A single, discoverable **toggle** lets any user switch to Advanced and back, instantly.
- Reuse LibreChat's existing show/hide mechanisms; introduce the smallest possible new concept.
- Mode is presentation-only: it composes with (never overrides) RBAC permissions and the
  `interface` config.

### Non-Goals (YAGNI for this iteration)
- **No admin-level default/lock** for the mode (that is Approach C / a future iteration). The
  mode is purely per-user for now.
- **No backend / API / schema changes.** Pure frontend.
- **No new RBAC permissions.** We do not touch `interface` config or the permission system.
- No granular per-feature user customization of what Basic contains (a fixed curated split).

## 4. Approach

**Chosen: Approach A — per-user `uiMode` client preference.**

LibreChat already knows how to hide nearly every complexity surface (via `startupConfig.interface`
→ RBAC → `useHasAccess`, and via `atomWithLocalStorage` UI-preference atoms). We add one new
preference atom, `uiMode`, and gate the **advanced surfaces** with an extra `isAdvanced` clause
that composes with the checks already present.

**Visibility rule (single invariant):**

```
Basic-set surface  → visible when (existing permission/interface checks pass)
Advanced surface   → visible when (existing permission/interface checks pass) AND isAdvanced
```

The mode can only *subtract* from what is already allowed. It can never add a surface the user
lacks permission for.

Rejected alternatives:
- **Approach B (`interface` config, global):** not per-user, no user toggle, and flipping
  `interface` flags also changes RBAC (access, not just presentation). Wrong tool for a per-user
  decluttering preference.
- **Approach C (hybrid per-user + admin default/lock):** adds backend plumbing we do not need
  yet. Revisit when selling to multiple customers who need enforced defaults.

## 5. Basic / Advanced Classification

### 🟢 Basic (default — kept visible)

| Surface | Notes |
|---|---|
| Message input + Send/Stop | Core |
| Attach file (image/document) | Familiar; ChatGPT parity |
| New chat · Chat history · Search | Core navigation |
| **Model selector — simplified** | Show admin-curated **modelSpecs only** (e.g. *Fast* / *Smart*). Hide the raw endpoint/model tree. If no specs configured → hide selector, use default model |
| Web Search toggle (single button) | Recognizable, high value |
| Mic / speech-to-text | Intuitive |
| Conversation starters | Helps new users start |
| Share conversation (basic share) | |
| Temporary chat (incognito-style) | Private, easy to grasp |
| Settings: General (theme, language), Account, Data (basic) | |

### 🔵 Advanced (hidden in Basic, shown when enabled)

| Group | Includes |
|---|---|
| Tools cluster (BadgeRow) | Tools dropdown, Code Interpreter, File Search, Skills, Artifacts, MCP select, user-created/draggable badges |
| Advanced model/agent selection | `@`-mention to switch model/agent/preset inline · Presets menu · preset editing |
| Model parameters | Parameters panel (temperature, top-p, max tokens, …) |
| Builders | Agent Builder · Assistant Builder · MCP Builder · Skills · Prompts (`$`) |
| Organization | Multi-conversation · Bookmarks/tags · Fork conversation |
| Memory & marketplace | Memories management panel (*memory keeps working in the background*; only the panel is hidden) · Agent Marketplace |
| Collaboration | Teams / Groups (RBAC) |
| Commands & advanced settings | Slash/command menus (`@ + / $`) · Settings "Chat" beta-toggles tab · Settings "Commands" tab · advanced Speech options · multi-format export |
| Side panel | Files panel and all builder panels |

**Confirmed border decisions:** Web Search, Mic, Temporary chat, and basic Share stay in **Basic**;
Bookmarks/tags and multi-format Export are **Advanced**.

## 6. Behavior & UX

### Toggle placement
- **Settings → General:** a segmented control **"Interface: Basic | Advanced"** at the top of the tab.
- **Account menu (avatar):** a secondary quick entry to switch mode, so users who need more can
  find it without digging into Settings.

### Switching behavior
- Switch is **instant, no reload** (reactive Recoil atom).
- Switching to Basic **only hides controls; it does not reset underlying state.** An in-flight
  conversation keeps its model and any active tools; returning to Advanced restores the previous
  badges/parameters exactly. This avoids silently disabling a tool that is mid-use.
- **Mode never grants access.** Any surface the user lacks permission for stays hidden in both
  modes (`allowed AND (isAdvanced OR basicSet)`).
- **Model selector in Basic:** the currently open conversation keeps its own model; a **new** chat
  uses the admin default spec/model (reuse the existing `modelSelect === false` default path).

### First-run transition (ship behavior)
- **Everyone (new and existing) defaults to Basic.**
- Show a **one-time** dismissible banner/toast on first load after deploy:
  *"Basic interface enabled — switch to Advanced anytime in Settings."* (localized). Gate it with a
  separate `uiModeIntroSeen` flag so it appears exactly once. This keeps existing power users from
  feeling lost.

## 7. Technical Design

All changes are in `/client`. No backend, no `packages/*` schema changes.

### 7.1 State
- Add atom in `client/src/store/settings.ts`:
  `uiMode = atomWithLocalStorage<'basic' | 'advanced'>('uiMode', 'basic')`
  Export through `client/src/store/index.ts`.
- Add `uiModeIntroSeen = atomWithLocalStorage<boolean>('uiModeIntroSeen', false)` for the banner.
- Add the localStorage key constants alongside the existing `LocalStorageKeys` usage.

### 7.2 Hook (single source of truth)
- New `client/src/hooks/useUIMode.ts` exporting `useUIMode()` → `{ mode, isBasic, isAdvanced, setMode }`.
- Every advanced touchpoint imports this hook; no ad-hoc localStorage reads.

### 7.3 Gating touchpoints (add `&& isAdvanced`, keep existing checks)
- `client/src/hooks/Nav/useSideNavLinks.ts` — gate Agent Builder, Assistant Builder, Skills,
  Prompts, Memories, Bookmarks, Teams, Parameters, MCP Builder, and Files panel behind
  `isAdvanced`. (`useUnifiedSidebarLinks.ts` inherits this.)
- `client/src/components/Chat/Input/BadgeRow.tsx` — hide the advanced badge cluster
  (ToolsDropdown, CodeInterpreter, FileSearch, Skills, Artifacts, MCPSelect, EditBadges/drag) in
  Basic. **Keep Web Search** (still permission-gated).
- `client/src/components/Chat/Header.tsx` — hide PresetsMenu, BookmarkMenu, AddMultiConvo in Basic.
  Keep TemporaryChat. Share stays; hide advanced export options (may need a `simplified` prop on
  `ExportAndShareMenu.tsx`).
- `client/src/components/Chat/Menus/Endpoints/ModelSelector.tsx` + `client/src/hooks/Endpoint/useEndpoints.ts`
  — in Basic, restrict `filteredEndpoints`/specs to modelSpecs only; render `null` if none.
- `client/src/components/Chat/Input/Mention.tsx` + `client/src/hooks/Input/useMentions.ts` — disable
  `@`/command-driven model/agent/preset switching in Basic.
- Command menus (`PromptsCommand.tsx`, `SkillsCommand.tsx`, `+`/`/`/`$` triggers) — disabled in Basic.
- Fork controls (`ForkSettings.tsx` + message fork buttons) — hidden in Basic.
- `client/src/components/Nav/AgentMarketplaceButton.tsx` — hidden in Basic.
- `client/src/components/Nav/Settings.tsx` — hide the "Chat" (beta toggles) and "Commands" tabs and
  advanced Speech options in Basic; keep General, Speech (basic subset), Data, Account, Balance.

### 7.4 Toggle UI
- `client/src/components/Nav/SettingsTabs/General/General.tsx` — add the segmented control using the
  existing settings-control patterns in that tab.
- `client/src/components/Nav/AccountSettings.tsx` — add the secondary quick switch entry.

### 7.5 Transition banner
- Render a one-time dismissible notice via the existing toast/notification system; set
  `uiModeIntroSeen = true` on show/dismiss.

### 7.6 Localization
- Add English keys only to `client/src/locales/en/translation.json`, `com_ui_` prefix, e.g.
  `com_ui_interface_mode`, `com_ui_mode_basic`, `com_ui_mode_advanced`, `com_ui_mode_intro_banner`.
- All new user-facing strings via `useLocalize()`.

## 8. Edge Cases
- **Permission vs mode:** advanced surface = `allowed AND isAdvanced`; basic surface = `allowed`.
  Mode subtracts only.
- **Active advanced tool while in Basic** (e.g. from an imported convo or a spec that forces a
  tool): the tool keeps working; its control is hidden. Acceptable.
- **No modelSpecs configured:** Basic hides the selector; new chats fall back to the existing
  default-model path used when `modelSelect === false`.
- **Deep links / `autoSubmitFromUrl`:** unaffected — governed by separate `interface` flags.

## 9. Testing
- **Unit:** `useUIMode` defaults to `basic`; `setMode` persists to localStorage; banner flag shows once.
- **Component:** BadgeRow renders only Web Search (subject to permission) in Basic and the full
  cluster in Advanced; Header hides Presets/Bookmark/MultiConvo in Basic; `useSideNavLinks` returns
  the Basic subset in Basic; Settings hides advanced tabs in Basic.
- **Invariant:** a permission-denied surface stays hidden in Advanced too (mode never grants access).
- **Interaction:** toggling in Settings/account menu updates the UI instantly without reload and
  preserves conversation state.

## 10. Rollout
- Pure frontend, low risk, easy rollback (default atom value).
- Ship via the standard NUFI release flow: feature branch → PR to `develop` → merge `develop` →
  `fork/main` → tag `nufi-vX.Y.Z`.
