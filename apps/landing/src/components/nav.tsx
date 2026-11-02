import { useEffect, useState } from 'react';
import { Link, useRouterState } from '@tanstack/react-router';
import { BrandMark } from './brand-mark';
import { Icon } from './icon';
import { SectionLink } from './section-link';
import { DOCS_URL } from '../content';

// Sections (on the home page) the nav scroll-spies for an active state.
const SPY_IDS = ['how', 'features'];

// Returns the id of the home-page section currently near the top of the
// viewport, or null. Only runs when `enabled` (i.e. on the home route).
function useActiveSection(enabled: boolean): string | null {
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) {
      setActive(null);
      return;
    }
    const els = SPY_IDS.map((id) => document.getElementById(id)).filter((el): el is HTMLElement => el !== null);
    if (els.length === 0) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length) setActive(visible[0].target.id);
      },
      { rootMargin: '-32% 0px -60% 0px', threshold: 0 },
    );
    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, [enabled]);
  return active;
}

export function Nav() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const onHome = pathname === '/';
  const onBlog = pathname === '/blog' || pathname.startsWith('/blog/');
  const activeSection = useActiveSection(onHome);
  const sectionCls = (id: string) => (onHome && activeSection === id ? 'is-active' : undefined);

  return (
    <header className="nav">
      <div className="shell nav__in">
        <Link className="brand" to="/" aria-label="NuFi Box home" onClick={close}>
          <BrandMark />
          <span className="brand__word">NuFi&nbsp;Box</span>
        </Link>
        <button className="nav__burger" aria-label="Menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <Icon name="menu" />
        </button>
        <nav className={open ? 'nav__links nav__links--open' : 'nav__links'}>
          <SectionLink id="how" className={sectionCls('how')} onNavigate={close}>
            How it works
          </SectionLink>
          <SectionLink id="features" className={sectionCls('features')} onNavigate={close}>
            Features
          </SectionLink>
          <Link to="/blog" onClick={close} className={onBlog ? 'is-active' : undefined}>
            Blog
          </Link>
          <a href={DOCS_URL} target="_blank" rel="noopener">
            Docs
          </a>
          <SectionLink id="contact" className="btn btn--primary" onNavigate={close}>
            Talk to us
          </SectionLink>
        </nav>
      </div>
    </header>
  );
}
