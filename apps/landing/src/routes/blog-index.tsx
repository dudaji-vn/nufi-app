import { Link } from '@tanstack/react-router';
import { Icon } from '../components/icon';

export function BlogIndex() {
  return (
    <main>
      <section className="blog-hd">
        <div className="shell">
          <Link className="back" to="/">
            <Icon name="arrow-l" /> Home
          </Link>
          <p className="eyebrow">NuFi Box · Blog</p>
          <h1>Use cases &amp; field notes</h1>
          <p>
            Real things we've run on a real box — GPU inference, department-drive RAG, cited answers. Every screenshot
            is unretouched.
          </p>
        </div>
      </section>

      <section className="section" style={{ paddingTop: 'clamp(2rem,5vw,3rem)' }}>
        <div className="shell">
          <div className="posts">
            <Link
              to="/blog/hr-private-document-qa"
              className="post-card post-card--link"
              aria-label="Read: We put our HR handbook on a box and let the team interrogate it"
            >
              <div className="post-card__media">
                <img src="/blog/security.png" alt="A cited answer about the company security policy" loading="lazy" />
              </div>
              <div className="post-card__body">
                <span className="post-card__kicker">Field notes · HR</span>
                <h3>We put our HR handbook on a box and let the team interrogate it</h3>
                <p>
                  One handbook, one box on the office network, and an afternoon of the questions people actually email
                  HR. Every answer quoted the document, and nothing left the building.
                </p>
                <span className="post-card__more">
                  Read the use case <Icon name="arrow" />
                </span>
              </div>
            </Link>

            <article className="post-card post-card--soon">
              <div className="post-card__media">
                <Icon name="book" size={40} className="" />
              </div>
              <div className="post-card__body">
                <span className="badge-soon">Coming soon</span>
                <h3>Legal over a stack of contracts</h3>
                <p>
                  Point a department at your contracts and ask what each one actually commits you to — on the box, with
                  citations.
                </p>
              </div>
            </article>

            <article className="post-card post-card--soon">
              <div className="post-card__media">
                <Icon name="console" size={40} className="" />
              </div>
              <div className="post-card__body">
                <span className="badge-soon">Coming soon</span>
                <h3>Support over the product docs</h3>
                <p>Answers your team can send straight to a customer, drawn from the manuals you already wrote.</p>
              </div>
            </article>

            <article className="post-card post-card--soon">
              <div className="post-card__media">
                <Icon name="gpu" size={40} className="" />
              </div>
              <div className="post-card__body">
                <span className="badge-soon">Coming soon</span>
                <h3>Finance over the SOPs</h3>
                <p>The box quotes the actual procedure from your own finance manuals, not a plausible-sounding paraphrase.</p>
              </div>
            </article>
          </div>
        </div>
      </section>
    </main>
  );
}
