import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';

export const baseOptions: BaseLayoutProps = {
  nav: {
    title: (
      <>
        <span
          aria-hidden
          style={{
            display: 'inline-block',
            width: 22,
            height: 22,
            borderRadius: 6,
            background:
              'linear-gradient(135deg, oklch(0.72 0.18 250), oklch(0.65 0.2 295))',
            marginRight: 8,
            verticalAlign: '-4px',
          }}
        />
        <span style={{ fontWeight: 700 }}>NUFI Docs</span>
      </>
    ),
  },
  // Section navigation lives in the sidebar tab switcher, so the top nav
  // only carries a link out to the live app (avoids duplicating the tabs).
  links: [{ text: 'Open App', url: 'https://chat.nufi.me', external: true }],
};
