import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';

export const baseOptions: BaseLayoutProps = {
  nav: {
    title: (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        {/* The source PNG has a white square backing; clip to a circle and
            scale up slightly so the gradient disc fills it — reads cleanly on
            both light and dark headers. */}
        <span
          style={{
            display: 'inline-block',
            width: 24,
            height: 24,
            borderRadius: '50%',
            overflow: 'hidden',
            flex: 'none',
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/nufi-icon.png"
            alt=""
            aria-hidden
            width={24}
            height={24}
            style={{
              display: 'block',
              transform: 'scale(1.2)',
              transformOrigin: 'center',
            }}
          />
        </span>
        <span style={{ fontWeight: 700 }}>NUFI Docs</span>
      </span>
    ),
  },
  // Section navigation lives in the sidebar tab switcher, so the top nav
  // only carries a link out to the live app (avoids duplicating the tabs).
  links: [{ text: 'Open App', url: 'https://chat.nufi.me', external: true }],
};
