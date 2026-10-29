import { Link } from '@tanstack/react-router';
import { BrandMark } from './brand-mark';
import { SectionLink } from './section-link';
import { DOCS_URL, EMAIL, MAILTO } from '../content';

export function Footer() {
  return (
    <footer className="foot on-navy">
      <div className="shell">
        <div className="foot__in">
          <div className="foot__brand">
            <Link className="brand" to="/" aria-label="NuFi Box home">
              <BrandMark style={{ height: '24px' }} />
              <span className="brand__word" style={{ color: '#fff' }}>
                NuFi&nbsp;Box
              </span>
            </Link>
            <p>A private, on-premise AI appliance. Your documents, your GPU, your network — nothing leaves the box.</p>
          </div>
          <div>
            <h4>Product</h4>
            <SectionLink id="how">How it works</SectionLink>
            <SectionLink id="features">Features</SectionLink>
            <SectionLink id="contact">Talk to us</SectionLink>
          </div>
          <div>
            <h4>Resources</h4>
            <Link to="/blog">Blog</Link>
            <a href={DOCS_URL} target="_blank" rel="noopener">
              Documentation
            </a>
          </div>
          <div>
            <h4>Company</h4>
            <a href={MAILTO}>{EMAIL}</a>
          </div>
        </div>
        <div className="foot__bar">
          <span>© {new Date().getFullYear()} NuFi</span>
          <span>Private AI appliance</span>
        </div>
      </div>
    </footer>
  );
}
