# Basic / Advanced UI Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-user Basic/Advanced UI mode (default Basic) that hides advanced surfaces for a simple, ChatGPT-like experience, with a user toggle.

**Architecture:** One Recoil `uiMode` atom persisted to localStorage (via the existing `atomWithLocalStorage` helper), read through a new `useUIMode()` hook. Every *advanced* surface adds an `isAdvanced` guard that composes with its existing permission/interface checks. The mode can only subtract from what a user is already permitted to see — it never grants access.

**Tech Stack:** React 18, Recoil, TypeScript, Jest + React Testing Library, Tailwind, `react-i18next` (`useLocalize`).

## Global Constraints

- All new backend code would be TypeScript in `/packages/api` — **but this feature is frontend-only; no backend, no `packages/*` schema changes.**
- All user-facing strings via `useLocalize()`; add English keys **only** to `client/src/locales/en/translation.json`, `com_ui_`/`com_nav_` prefix.
- Never use `any`. Explicit types for all params/returns.
- Visibility invariant: `advanced surface visible ⇔ (existing permission/interface checks) AND isAdvanced`; `basic surface visible ⇔ (existing checks)`.
- Follow existing import ordering and file-naming conventions (single-word file names where possible).
- Frequent commits: one commit per task.

## Plan-level simplifications vs. spec (please confirm before executing)

These trim fragile edges without changing the user-visible intent:
1. **Speech settings tab stays fully in Basic** (STT/TTS is basic-friendly and matches "Mic in Basic"). Only the **Chat** (beta toggles) and **Commands** tabs are hidden in Basic. No edits inside the Speech component.
2. **Share/Export menu stays intact in Basic** (basic share). We do **not** separately hide multi-format export — that would require threading a `simplified` prop through `ExportAndShareMenu`. Low value, higher risk.
3. **Slash/`$`/`+`/`@` command gating** is scoped to the `@`-mention model/agent/preset switcher (the genuinely confusing one). The `$`/`/` prompt & skill commands lose their discovery surfaces anyway because the Prompts/Skills side-panels (Task 5) and the Commands settings tab (Task 10) are hidden in Basic. Fully disabling every command trigger is deferred unless testing shows it's needed.

---

## File Structure

**New files**
- `client/src/hooks/useUIMode.ts` — the mode hook (`{ mode, isBasic, isAdvanced, setMode }`).
- `client/src/hooks/useUIMode.spec.tsx` — hook tests.
- `client/src/components/Nav/UIModeIntroBanner.tsx` — one-time transition banner.
- `client/src/components/Nav/UIModeIntroBanner.spec.tsx` — banner tests.

**Modified files**
- `client/src/store/settings.ts` — add `uiMode`, `uiModeIntroSeen` atoms.
- `client/src/hooks/index.ts` — re-export `useUIMode`.
- `client/src/components/Nav/SettingsTabs/General/General.tsx` — add the mode selector.
- `client/src/components/Nav/AccountSettings.tsx` — add a quick mode switch.
- `client/src/hooks/Nav/useSideNavLinks.ts` — gate advanced panels.
- `client/src/components/Chat/Input/BadgeRow.tsx` — gate advanced badges (keep Web Search).
- `client/src/components/Chat/Header.tsx` — gate Presets/Bookmark/MultiConvo menus.
- `client/src/hooks/Endpoint/useEndpoints.ts` — Basic → specs-only model selection.
- `client/src/components/Chat/Input/Mention.tsx` and/or `client/src/hooks/Input/useMentions.ts` — disable model/agent switch in Basic.
- `client/src/components/Nav/Settings.tsx` — hide Chat & Commands tabs in Basic.
- Fork controls + `client/src/components/Nav/AgentMarketplaceButton.tsx` — hide in Basic.
- `client/src/locales/en/translation.json` — new keys.

---

### Task 1: `uiMode` state + `useUIMode` hook

**Files:**
- Modify: `client/src/store/settings.ts`
- Create: `client/src/hooks/useUIMode.ts`
- Modify: `client/src/hooks/index.ts`
- Test: `client/src/hooks/useUIMode.spec.tsx`

**Interfaces:**
- Produces:
  - `store.uiMode: RecoilState<UIMode>` where `type UIMode = 'basic' | 'advanced'` (default `'basic'`)
  - `store.uiModeIntroSeen: RecoilState<boolean>` (default `false`)
  - `useUIMode(): { mode: UIMode; isBasic: boolean; isAdvanced: boolean; setMode: (m: UIMode) => void }`

- [ ] **Step 1: Add atoms to the store**

In `client/src/store/settings.ts`, inside `localStorageAtoms`, add after the `UsernameDisplay` line:

```typescript
  // UI mode
  uiMode: atomWithLocalStorage<'basic' | 'advanced'>('uiMode', 'basic'),
  uiModeIntroSeen: atomWithLocalStorage<boolean>('uiModeIntroSeen', false),
```

- [ ] **Step 2: Write the failing hook test**

Create `client/src/hooks/useUIMode.spec.tsx`:

```tsx
import { renderHook, act } from '@testing-library/react';
import { RecoilRoot } from 'recoil';
import useUIMode from './useUIMode';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <RecoilRoot>{children}</RecoilRoot>
);

describe('useUIMode', () => {
  beforeEach(() => localStorage.clear());

  it('defaults to basic', () => {
    const { result } = renderHook(() => useUIMode(), { wrapper });
    expect(result.current.mode).toBe('basic');
    expect(result.current.isBasic).toBe(true);
    expect(result.current.isAdvanced).toBe(false);
  });

  it('setMode switches to advanced and persists', () => {
    const { result } = renderHook(() => useUIMode(), { wrapper });
    act(() => result.current.setMode('advanced'));
    expect(result.current.isAdvanced).toBe(true);
    expect(localStorage.getItem('uiMode')).toBe(JSON.stringify('advanced'));
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd client && npx jest src/hooks/useUIMode.spec.tsx`
Expected: FAIL — cannot find module `./useUIMode`.

- [ ] **Step 4: Create the hook**

Create `client/src/hooks/useUIMode.ts`:

```typescript
import { useRecoilState } from 'recoil';
import store from '~/store';

export type UIMode = 'basic' | 'advanced';

export default function useUIMode() {
  const [mode, setMode] = useRecoilState<UIMode>(store.uiMode);
  return {
    mode,
    isBasic: mode === 'basic',
    isAdvanced: mode === 'advanced',
    setMode,
  };
}
```

- [ ] **Step 5: Export from the hooks barrel**

In `client/src/hooks/index.ts`, add an export line following the file's existing pattern (match how neighbors are re-exported):

```typescript
export { default as useUIMode } from './useUIMode';
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd client && npx jest src/hooks/useUIMode.spec.tsx`
Expected: PASS (both tests).

- [ ] **Step 7: Commit**

```bash
git add client/src/store/settings.ts client/src/hooks/useUIMode.ts client/src/hooks/useUIMode.spec.tsx client/src/hooks/index.ts
git commit -m "feat(ui-mode): add uiMode state and useUIMode hook"
```

---

### Task 2: Mode selector in Settings → General

**Files:**
- Modify: `client/src/components/Nav/SettingsTabs/General/General.tsx`
- Modify: `client/src/locales/en/translation.json`
- Test: `client/src/components/Nav/SettingsTabs/General/General.spec.tsx` (create if absent)

**Interfaces:**
- Consumes: `useUIMode` (Task 1), the `Dropdown` component pattern already used by `ThemeSelector`.

- [ ] **Step 1: Add localization keys**

In `client/src/locales/en/translation.json`, add (alphabetical placement not required, keep valid JSON):

```json
"com_nav_ui_mode": "Interface",
"com_nav_ui_mode_basic": "Basic",
"com_nav_ui_mode_advanced": "Advanced",
"com_ui_mode_intro_banner": "Basic interface enabled — switch to Advanced anytime in Settings.",
"com_ui_mode_intro_dismiss": "Got it"
```

- [ ] **Step 2: Write the failing test**

Create `client/src/components/Nav/SettingsTabs/General/General.spec.tsx`:

```tsx
import { render, screen, fireEvent } from 'test/layout-test-utils';
import General from './General';

describe('General settings — UI mode selector', () => {
  beforeEach(() => localStorage.clear());

  it('renders the Interface selector defaulting to Basic', () => {
    render(<General />);
    expect(screen.getByText('Interface')).toBeInTheDocument();
    expect(screen.getByTestId('ui-mode-selector')).toHaveTextContent('Basic');
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd client && npx jest src/components/Nav/SettingsTabs/General/General.spec.tsx`
Expected: FAIL — no element with text "Interface" / testId `ui-mode-selector`.

- [ ] **Step 4: Add the selector**

In `General.tsx`, import the hook and add a `UIModeSelector` mirroring `ThemeSelector`. Add near the top of the imports:

```tsx
import { useUIMode } from '~/hooks';
```

Add this component above `function General()`:

```tsx
export const UIModeSelector = () => {
  const localize = useLocalize();
  const { mode, setMode } = useUIMode();
  const labelId = 'ui-mode-selector-label';
  const options = [
    { value: 'basic', label: localize('com_nav_ui_mode_basic') },
    { value: 'advanced', label: localize('com_nav_ui_mode_advanced') },
  ];
  return (
    <div className="flex items-center justify-between">
      <div id={labelId}>{localize('com_nav_ui_mode')}</div>
      <Dropdown
        value={mode}
        onChange={(value: string) => setMode(value as 'basic' | 'advanced')}
        options={options}
        sizeClasses="w-[180px]"
        testId="ui-mode-selector"
        className="z-50"
        aria-labelledby={labelId}
      />
    </div>
  );
};
```

Then render it as the first row inside the returned `<div className="flex flex-col gap-3 ...">`, before the `ThemeSelector` block:

```tsx
      <div className="pb-3">
        <UIModeSelector />
      </div>
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd client && npx jest src/components/Nav/SettingsTabs/General/General.spec.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/Nav/SettingsTabs/General/General.tsx client/src/components/Nav/SettingsTabs/General/General.spec.tsx client/src/locales/en/translation.json
git commit -m "feat(ui-mode): add Interface mode selector to General settings"
```

---

### Task 3: Quick mode switch in the account menu

**Files:**
- Read then Modify: `client/src/components/Nav/AccountSettings.tsx`
- Test: extend an existing `AccountSettings` test or add `AccountSettings.spec.tsx`

**Interfaces:**
- Consumes: `useUIMode` (Task 1).

- [ ] **Step 1: Read the file to learn its menu-item pattern**

Run: open `client/src/components/Nav/AccountSettings.tsx`. Identify how existing menu items are rendered (it uses a dropdown/menu list of rows with an icon + label + onClick).

- [ ] **Step 2: Write the failing test**

Add to (or create) `client/src/components/Nav/AccountSettings.spec.tsx`:

```tsx
import { render, screen, fireEvent } from 'test/layout-test-utils';
import AccountSettings from './AccountSettings';

it('toggles UI mode from the account menu', async () => {
  localStorage.clear();
  render(<AccountSettings />);
  // open the menu per the component's trigger, then:
  const item = await screen.findByTestId('account-ui-mode-toggle');
  fireEvent.click(item);
  expect(localStorage.getItem('uiMode')).toBe(JSON.stringify('advanced'));
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd client && npx jest src/components/Nav/AccountSettings.spec.tsx`
Expected: FAIL — no `account-ui-mode-toggle`.

- [ ] **Step 4: Add the menu item**

Add near the other hooks in the component:

```tsx
const { isAdvanced, setMode } = useUIMode();
```

Add a menu row alongside the existing items, following the file's row markup, with:
- `data-testid="account-ui-mode-toggle"`
- label: `localize(isAdvanced ? 'com_nav_ui_mode_basic' : 'com_nav_ui_mode_advanced')` (offer the *other* mode)
- `onClick={() => setMode(isAdvanced ? 'basic' : 'advanced')}`

Import: `import { useUIMode } from '~/hooks';`

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd client && npx jest src/components/Nav/AccountSettings.spec.tsx`
Expected: PASS. (Adjust the menu-open interaction in the test to match the component's trigger.)

- [ ] **Step 6: Commit**

```bash
git add client/src/components/Nav/AccountSettings.tsx client/src/components/Nav/AccountSettings.spec.tsx
git commit -m "feat(ui-mode): add quick mode switch to account menu"
```

---

### Task 4: One-time transition banner

**Files:**
- Create: `client/src/components/Nav/UIModeIntroBanner.tsx`
- Test: `client/src/components/Nav/UIModeIntroBanner.spec.tsx`
- Modify: the top-level authenticated layout to mount the banner (e.g. `client/src/components/Chat/ChatView.tsx` or the root route component — pick the component that wraps all chat screens).

**Interfaces:**
- Consumes: `store.uiModeIntroSeen`, `store.uiMode` (Task 1).

- [ ] **Step 1: Write the failing test**

Create `client/src/components/Nav/UIModeIntroBanner.spec.tsx`:

```tsx
import { render, screen, fireEvent } from 'test/layout-test-utils';
import UIModeIntroBanner from './UIModeIntroBanner';

describe('UIModeIntroBanner', () => {
  beforeEach(() => localStorage.clear());

  it('shows once for a default (basic) user and hides after dismiss', () => {
    const { rerender } = render(<UIModeIntroBanner />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('ui-mode-intro-dismiss'));
    expect(localStorage.getItem('uiModeIntroSeen')).toBe(JSON.stringify(true));
    rerender(<UIModeIntroBanner />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('does not show if already seen', () => {
    localStorage.setItem('uiModeIntroSeen', JSON.stringify(true));
    render(<UIModeIntroBanner />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd client && npx jest src/components/Nav/UIModeIntroBanner.spec.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the banner**

Create `client/src/components/Nav/UIModeIntroBanner.tsx`:

```tsx
import { useRecoilState } from 'recoil';
import { useLocalize } from '~/hooks';
import store from '~/store';

export default function UIModeIntroBanner() {
  const localize = useLocalize();
  const [seen, setSeen] = useRecoilState(store.uiModeIntroSeen);

  if (seen) {
    return null;
  }

  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 border-b border-border-light bg-surface-secondary px-4 py-2 text-sm text-text-primary"
    >
      <span>{localize('com_ui_mode_intro_banner')}</span>
      <button
        type="button"
        data-testid="ui-mode-intro-dismiss"
        className="rounded-md px-2 py-1 font-medium text-text-secondary hover:text-text-primary"
        onClick={() => setSeen(true)}
      >
        {localize('com_ui_mode_intro_dismiss')}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx jest src/components/Nav/UIModeIntroBanner.spec.tsx`
Expected: PASS.

- [ ] **Step 5: Mount the banner globally**

In the top-level chat layout component (the one rendering all chat screens), import and render `<UIModeIntroBanner />` at the very top of its returned tree so it appears once above the app chrome. Verify manually that it renders on first load and disappears after dismiss.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/Nav/UIModeIntroBanner.tsx client/src/components/Nav/UIModeIntroBanner.spec.tsx client/src/components/Chat/ChatView.tsx
git commit -m "feat(ui-mode): one-time Basic-interface intro banner"
```

---

### Task 5: Gate advanced side-nav panels

**Files:**
- Modify: `client/src/hooks/Nav/useSideNavLinks.ts`
- Test: `client/src/hooks/Nav/useSideNavLinks.spec.tsx` (create)

**Interfaces:**
- Consumes: `useUIMode` (Task 1).

- [ ] **Step 1: Write the failing test**

Create `client/src/hooks/Nav/useSideNavLinks.spec.tsx`. Render the hook with `RecoilRoot` + the app's query/auth providers (mirror an existing hook test that needs `useHasAccess`; if simpler, mock `~/hooks` `useHasAccess` to return `true`). Assert:

```tsx
// In basic mode, none of the advanced panel ids are present:
expect(ids).not.toEqual(expect.arrayContaining(['prompts', 'memories', 'bookmarks', 'files']));
// After setMode('advanced'), they appear (given permissions granted).
```

Keep the test minimal: mock `useHasAccess` to `true`, mock `useMCPServerManager`/`useGetAgentsConfig`/`useAgentCapabilities` to benign values, and pass a minimal `endpointsConfig`/`interfaceConfig`. Assert the `files` link is absent in basic and present in advanced.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd client && npx jest src/hooks/Nav/useSideNavLinks.spec.tsx`
Expected: FAIL — `files` present in basic (no gating yet).

- [ ] **Step 3: Add the mode gate**

In `useSideNavLinks.ts`:

Add the import with the other `~/hooks` imports:

```typescript
import { useUIMode } from '~/hooks';
```

Inside the hook body, before `const Links = useMemo(...)`:

```typescript
  const { isAdvanced } = useUIMode();
```

Wrap each advanced link's `push` condition with `isAdvanced &&`. Concretely:
- Agent builder `if` → prepend `isAdvanced &&`
- Assistant builder `if` → prepend `isAdvanced &&`
- Skills `if (hasAccessToSkills && skillsEnabled)` → `if (isAdvanced && hasAccessToSkills && skillsEnabled)`
- Prompts `if (hasAccessToPrompts)` → `if (isAdvanced && hasAccessToPrompts)`
- Memories `if (...)` → prepend `isAdvanced &&`
- Bookmarks `if (hasAccessToBookmarks)` → `if (isAdvanced && hasAccessToBookmarks)`
- Teams `if (hasAccessToTeams)` → `if (isAdvanced && hasAccessToTeams)`
- Files — wrap the unconditional push: `if (isAdvanced) { links.push({ ...files }); }`
- Parameters `if (...)` → prepend `isAdvanced &&`
- MCP builder `if (...)` → prepend `isAdvanced &&`
- Leave the `hide-panel` link unchanged.

Add `isAdvanced` to the `useMemo` dependency array.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx jest src/hooks/Nav/useSideNavLinks.spec.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/Nav/useSideNavLinks.ts client/src/hooks/Nav/useSideNavLinks.spec.tsx
git commit -m "feat(ui-mode): hide advanced side-nav panels in Basic"
```

---

### Task 6: Gate advanced chat-input badges (keep Web Search)

**Files:**
- Modify: `client/src/components/Chat/Input/BadgeRow.tsx`
- Test: `client/src/components/Chat/Input/BadgeRow.spec.tsx` (create)

**Interfaces:**
- Consumes: `useUIMode` (Task 1).

- [ ] **Step 1: Write the failing test**

Create `client/src/components/Chat/Input/BadgeRow.spec.tsx`. Render `BadgeRow` with `showEphemeralBadges` and the required providers (mirror an existing input test). Assert that in Basic the container does not render the `ToolsDropdown` (query by its role/testid) and does render `WebSearch`; in Advanced (`setMode('advanced')`) the advanced badges appear. If badge children lack testids, assert on the count of `.badge-icon` elements or on accessible names. Keep assertions resilient.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd client && npx jest src/components/Chat/Input/BadgeRow.spec.tsx`
Expected: FAIL — advanced badges present in Basic.

- [ ] **Step 3: Add the mode gate**

In `BadgeRow.tsx`:

Add import:

```typescript
import { useUIMode } from '~/hooks';
```

Inside `function BadgeRow(...)`, after the other hooks:

```typescript
  const { isAdvanced } = useUIMode();
```

Change the JSX:
- `{showEphemeralBadges === true && <ToolsDropdown />}` → `{showEphemeralBadges === true && isAdvanced && <ToolsDropdown />}`
- Wrap the draggable badges block so user badges/editing only show in Advanced. Replace the `{tempBadges.map(...)}` block and the trailing ghost-insert block with `{isAdvanced && (<> ...that JSX... </>)}`.
- The ephemeral cluster keeps Web Search, gates the rest:

```tsx
        {showEphemeralBadges === true && (
          <>
            <WebSearch />
            {isAdvanced && (
              <>
                <CodeInterpreter />
                <FileSearch />
                <Skills />
                <Artifacts />
                <MCPSelect />
              </>
            )}
          </>
        )}
```

- The floating `ghostBadge` block (drag preview) can be left; it only renders while dragging, which is Advanced-only anyway.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx jest src/components/Chat/Input/BadgeRow.spec.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/Chat/Input/BadgeRow.tsx client/src/components/Chat/Input/BadgeRow.spec.tsx
git commit -m "feat(ui-mode): hide advanced input badges in Basic, keep Web Search"
```

---

### Task 7: Gate Header menus (Presets, Bookmark, Multi-convo)

**Files:**
- Read then Modify: `client/src/components/Chat/Header.tsx`
- Test: `client/src/components/Chat/Header.spec.tsx` (create or extend)

**Interfaces:**
- Consumes: `useUIMode` (Task 1).

- [ ] **Step 1: Read `Header.tsx`** to locate where `PresetsMenu`, `BookmarkMenu`, and `AddMultiConvo` are rendered and their existing gating conditions.

- [ ] **Step 2: Write the failing test**

Create `client/src/components/Chat/Header.spec.tsx`. Render `Header` with providers; assert `PresetsMenu`/`BookmarkMenu`/`AddMultiConvo` (by testid or accessible name) are absent in Basic and present in Advanced when their permissions/config allow. Mock permission hooks to `true`.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd client && npx jest src/components/Chat/Header.spec.tsx`
Expected: FAIL — menus present in Basic.

- [ ] **Step 4: Add the gate**

Add `import { useUIMode } from '~/hooks';` and `const { isAdvanced } = useUIMode();` in the component. Prepend `isAdvanced &&` to the render conditions for `PresetsMenu`, `BookmarkMenu`, and `AddMultiConvo`. Leave `ModelSelector` (handled in Task 8), `ExportAndShareMenu`, and `TemporaryChat` unchanged.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd client && npx jest src/components/Chat/Header.spec.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/Chat/Header.tsx client/src/components/Chat/Header.spec.tsx
git commit -m "feat(ui-mode): hide Presets/Bookmark/Multi-convo header menus in Basic"
```

---

### Task 8: Basic mode → simplified model selection (specs only)

**Files:**
- Read then Modify: `client/src/hooks/Endpoint/useEndpoints.ts`
- Test: `client/src/hooks/Endpoint/useEndpoints.spec.tsx` (create or extend)

**Interfaces:**
- Consumes: `useUIMode` (Task 1). Reuses the existing `interface.modelSelect === false` code path that empties `filteredEndpoints` while keeping `modelSpecs`.

- [ ] **Step 1: Read `useEndpoints.ts`** and find the `modelSelect` check that produces `filteredEndpoints` (returns empty when `modelSelect === false`), and where `modelSpecs` are assembled.

- [ ] **Step 2: Write the failing test**

Create `client/src/hooks/Endpoint/useEndpoints.spec.tsx`. Provide a config with ≥1 endpoint and ≥1 modelSpec. Assert: in Basic, `filteredEndpoints` is empty (only specs remain); in Advanced, endpoints are present. Mock `useHasAccess` and startup config as needed.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd client && npx jest src/hooks/Endpoint/useEndpoints.spec.tsx`
Expected: FAIL — endpoints present in Basic.

- [ ] **Step 4: Add the gate**

Add `import { useUIMode } from '~/hooks';` and `const { isBasic } = useUIMode();`. At the existing `modelSelect` gate, treat Basic as "hide raw endpoints": compute an effective flag, e.g. change the condition that empties `filteredEndpoints` from `modelSelect === false` to `modelSelect === false || isBasic`. Do **not** touch the `modelSpecs` assembly (specs stay visible). Add `isBasic` to any relevant memo deps.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd client && npx jest src/hooks/Endpoint/useEndpoints.spec.tsx`
Expected: PASS.

- [ ] **Step 6: Manual check**

Verify `ModelSelector` renders only the admin specs in Basic (or nothing if no specs), and a new chat still opens with a working default model.

- [ ] **Step 7: Commit**

```bash
git add client/src/hooks/Endpoint/useEndpoints.ts client/src/hooks/Endpoint/useEndpoints.spec.tsx
git commit -m "feat(ui-mode): restrict model selection to specs in Basic"
```

---

### Task 9: Disable `@`-mention model/agent/preset switch in Basic

**Files:**
- Read then Modify: `client/src/hooks/Input/useMentions.ts` and/or `client/src/components/Chat/Input/Mention.tsx`
- Test: alongside the modified unit.

**Interfaces:**
- Consumes: `useUIMode` (Task 1).

- [ ] **Step 1: Read `useMentions.ts` and `Mention.tsx`** to find where the mention options for models/agents/presets are assembled and where the popover is enabled.

- [ ] **Step 2: Write the failing test**

Add a spec for the modified unit asserting that in Basic the model/agent/preset mention options are empty (or the popover is disabled), and populated in Advanced.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd client && npx jest <path to the new spec>`
Expected: FAIL.

- [ ] **Step 4: Add the gate**

Add `import { useUIMode } from '~/hooks';` and `const { isBasic } = useUIMode();`. Return empty mention options (or `open={false}` on the popover) when `isBasic`. Keep any non-switching mention behavior intact per the file's structure.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd client && npx jest <path to the new spec>`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/hooks/Input/useMentions.ts client/src/components/Chat/Input/Mention.tsx <spec>
git commit -m "feat(ui-mode): disable @-mention model/agent switch in Basic"
```

---

### Task 10: Hide advanced Settings tabs in Basic

**Files:**
- Modify: `client/src/components/Nav/Settings.tsx`
- Test: `client/src/components/Nav/Settings.spec.tsx` (create or extend)

**Interfaces:**
- Consumes: `useUIMode` (Task 1).

- [ ] **Step 1: Write the failing test**

Create `client/src/components/Nav/Settings.spec.tsx`. Render `<Settings open onOpenChange={() => {}} />`. Assert the "Chat" and "Commands" tab triggers are absent in Basic and present in Advanced. (Match by localized labels `com_nav_setting_chat` → "Chat", `com_nav_commands` → "Commands".)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd client && npx jest src/components/Nav/Settings.spec.tsx`
Expected: FAIL — tabs present in Basic.

- [ ] **Step 3: Add the gate**

In `Settings.tsx`:

Add `import { useUIMode } from '~/hooks';` and `const { isAdvanced } = useUIMode();`.

Make the `CHAT` and `COMMANDS` entries conditional in **all three** places that list them:
1. In `handleKeyDown`'s local `tabs` array — spread them only when advanced:
   ```tsx
   SettingsTabValues.GENERAL,
   ...(isAdvanced ? [SettingsTabValues.CHAT, SettingsTabValues.COMMANDS] : []),
   SettingsTabValues.SPEECH,
   ```
2. In the `settingsTabs` array — replace the two static `{ value: CHAT ... }` and `{ value: COMMANDS ... }` objects with a conditional spread:
   ```tsx
   ...(isAdvanced
     ? [
         { value: SettingsTabValues.CHAT, icon: <MessageSquare className="icon-sm" aria-hidden="true" />, label: 'com_nav_setting_chat' as TranslationKeys },
         { value: SettingsTabValues.COMMANDS, icon: <Command className="icon-sm" aria-hidden="true" />, label: 'com_nav_commands' as TranslationKeys },
       ]
     : []),
   ```
3. In the `Tabs.Content` block — wrap the `CHAT` and `COMMANDS` `<Tabs.Content>` with `{isAdvanced && (...)}`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx jest src/components/Nav/Settings.spec.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/Nav/Settings.tsx client/src/components/Nav/Settings.spec.tsx
git commit -m "feat(ui-mode): hide Chat and Commands settings tabs in Basic"
```

---

### Task 11: Hide Fork controls and Agent Marketplace in Basic

**Files:**
- Read then Modify: `client/src/components/Nav/AgentMarketplaceButton.tsx` and the message Fork control (`client/src/components/Chat/Messages/...` fork button; find via grep for `ForkSettings`/`fork`).
- Test: alongside each modified unit.

**Interfaces:**
- Consumes: `useUIMode` (Task 1).

- [ ] **Step 1: Locate the components**

Run: `cd client && grep -rl "ForkSettings\|AgentMarketplaceButton" src/components`

- [ ] **Step 2: Write failing tests**

For `AgentMarketplaceButton`, assert it renders `null` in Basic and content in Advanced. For the message fork control, assert the fork affordance is absent in Basic.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd client && npx jest src/components/Nav/AgentMarketplaceButton.spec.tsx`
Expected: FAIL.

- [ ] **Step 4: Add the gates**

In each component: `import { useUIMode } from '~/hooks';`, `const { isAdvanced } = useUIMode();`, and early-`return null` (or prepend `isAdvanced &&` to the render condition) when not advanced.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd client && npx jest src/components/Nav/AgentMarketplaceButton.spec.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/Nav/AgentMarketplaceButton.tsx <fork files> <specs>
git commit -m "feat(ui-mode): hide Fork controls and Agent Marketplace in Basic"
```

---

### Task 12: End-to-end verification & lint

**Files:** none (verification only).

- [ ] **Step 1: Typecheck & lint the client**

Run: `cd client && npx tsc --noEmit && npx eslint src --ext .ts,.tsx`
Expected: no errors introduced by the new/modified files.

- [ ] **Step 2: Run the feature test suite**

Run: `cd client && npx jest src/hooks/useUIMode.spec.tsx src/components/Nav/UIModeIntroBanner.spec.tsx src/hooks/Nav/useSideNavLinks.spec.tsx src/components/Chat/Input/BadgeRow.spec.tsx src/components/Nav/Settings.spec.tsx`
Expected: all PASS.

- [ ] **Step 3: Manual smoke test (argent Chromium or `npm run frontend:dev`)**

With backend running and `npm run frontend:dev`:
- Fresh localStorage → app loads in Basic; intro banner shows once; dismiss it.
- Basic hides: tools/badges (except Web Search), side-nav builders/prompts/memories/bookmarks/teams/files/parameters, Presets/Bookmark/Multi-convo header menus, raw model tree (specs only), Chat & Commands settings tabs, `@`-mention switch, Fork, Marketplace.
- Switch to Advanced in Settings → General: everything reappears (subject to permissions). Switch back to Basic: instant, no reload, conversation state preserved.
- Reload → banner does not reappear; chosen mode persists.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A
git commit -m "chore(ui-mode): lint/typecheck fixes and verification"
```

---

## Self-Review

- **Spec coverage:** Approach A (atom + hook) → Task 1. Toggle in Settings + account menu → Tasks 2–3. Default Basic + one-time banner → Tasks 1 & 4. Basic/Advanced classification → Tasks 5–11 (side nav, badges, header, model selector, mention, settings tabs, fork, marketplace). Invariant "mode never grants access" → every gate ANDs with existing permission checks. Persistence → `atomWithLocalStorage` (Task 1). Instant switch, no reload, state preserved → reactive atoms; verified in Task 12. Memory keeps working while its panel is hidden → we gate only the side-nav panel (Task 5), not memory runtime.
- **Deviations (flagged above):** Speech tab kept in Basic; export-format not separately hidden; `$`/`/`/`+` command triggers not force-disabled (discovery removed via Tasks 5 & 10). Confirm these are acceptable.
- **Type consistency:** `UIMode = 'basic' | 'advanced'` and `useUIMode(): { mode, isBasic, isAdvanced, setMode }` are used identically across all tasks. Atom keys `uiMode` / `uiModeIntroSeen` match localStorage assertions in tests.
- **Placeholder scan:** New-code tasks (1–4) contain complete code. Modification tasks (5–11) give exact files, exact anchors, and the exact clause to add, plus test intent — no "TODO"/"implement later".
