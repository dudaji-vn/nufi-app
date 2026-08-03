import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';

export const baseOptions: BaseLayoutProps = {
  nav: {
    title: (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        {/* The wordmark already reads "NUFI", so the text beside it is only
            "Docs" — the same lockup the app, console and admin panel use.
            Kept as a shared asset rather than inlined so a brand change lands
            everywhere at once; `.nufi-mark` in global.css reverses it to white
            for the dark header, where the navy has no contrast. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/nufi-logo.svg"
          alt="NUFI"
          className="nufi-mark"
          style={{ display: 'block', height: 22, width: 'auto', flex: 'none' }}
        />
        <span style={{ fontWeight: 700 }}>Docs</span>
      </span>
    ),
  },
  // Section navigation lives in the sidebar tab switcher, so the top nav
  // only carries a link out to the live app (avoids duplicating the tabs).
  links: [{ text: 'Open App', url: 'https://chat.nufi.me', external: true }],
};
