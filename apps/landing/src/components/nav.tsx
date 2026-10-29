import { useState } from 'react';
import { Link } from '@tanstack/react-router';
import { BrandMark } from './brand-mark';
import { Icon } from './icon';
import { SectionLink } from './section-link';
import { DOCS_URL } from '../content';

export function Nav() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

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
          <SectionLink id="how" onNavigate={close}>
            How it works
          </SectionLink>
          <SectionLink id="features" onNavigate={close}>
            Features
          </SectionLink>
          <Link to="/blog" onClick={close}>
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
