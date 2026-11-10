import { Link } from '@tanstack/react-router';
import { useHead } from '../components/head';
import { POSTS } from '../posts/registry';
import { areaSummary, formatDate, postsInSeries, type Area } from '../posts/taxonomy';

// One area of the blog: its series as numbered chapter lists.
export function BlogArea({ area }: { area: Area }) {
  useHead(`${area.name} — NuFi blog`, area.intro);
  return (
    <main className="lib">
      <section className="shell lib-hd">
        <nav className="crumbs" aria-label="Breadcrumb">
          <Link to="/blog">Blog</Link>
          <span aria-hidden="true">›</span>
          <span>{area.name}</span>
        </nav>
        <h1 className="lib-area-title">{area.name}</h1>
        <p className="lib-area-lead">{area.intro}</p>
      </section>
      <div className="shell">
        {areaSummary(POSTS, area).map(({ series, count }, i) => (
          <section key={series.id} id={series.id} className="lib-area lib-chapter">
            <p className="lib-label">
              Series {String(i + 1).padStart(2, '0')} · {count > 0 ? `${count} ${count === 1 ? 'post' : 'posts'}` : series.status}
            </p>
            <h2 className={count === 0 ? 'is-empty' : undefined}>{series.name}</h2>
            <p className="lib-area__intro">{series.intro}</p>
            {count > 0 ? (
              <ol className="chapters">
                {postsInSeries(POSTS, area.id, series.id).map((p, n) => (
                  <li key={p.slug}>
                    <span className="chapters__n">{String(n + 1).padStart(2, '0')}</span>
                    <div>
                      <h3>
                        <Link to="/blog/$slug" params={{ slug: p.slug }}>
                          {p.title}
                        </Link>
                      </h3>
                      <p className="lib-post__sum">{p.summary}</p>
                    </div>
                    <p className="lib-meta chapters__meta">
                      <time dateTime={p.date}>{formatDate(p.date)}</time>
                      <br />
                      {p.readingMinutes} min{p.video ? ' · ▶ video' : ''}
                    </p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="chapters__empty">{series.status === 'next' ? 'Next in this series.' : 'Coming soon.'}</p>
            )}
          </section>
        ))}
      </div>
    </main>
  );
}
