import { Link } from '@tanstack/react-router';
import type { PostMeta } from '../../posts/registry';
import { areaSummary, type Area } from '../../posts/taxonomy';

const STATUS_LABEL = { next: 'next', soon: 'soon' } as const;

// An area shown as a folder: its series inside, with post counts (or "next" / "soon").
export function AreaFolder({ area, posts, index }: { area: Area; posts: PostMeta[]; index: number }) {
  const total = posts.filter((p) => p.area === area.id).length;
  return (
    <section className="lib-area" aria-labelledby={`area-${area.id}`}>
      <p className="lib-label">
        Area {String(index + 1).padStart(2, '0')} · {total} {total === 1 ? 'post' : 'posts'}
      </p>
      <h2 id={`area-${area.id}`}>
        <Link to="/blog/$slug" params={{ slug: area.id }}>
          {area.name}
        </Link>
      </h2>
      <p className="lib-area__intro">{area.intro}</p>
      <ul className="lib-series">
        {areaSummary(posts, area).map(({ series, count }) => (
          <li key={series.id} className={count === 0 ? 'is-empty' : undefined}>
            {count > 0 ? (
              <Link to="/blog/$slug" params={{ slug: area.id }} hash={series.id}>
                {series.name}
              </Link>
            ) : (
              <span>{series.name}</span>
            )}
            <span className="lib-series__n">
              {count > 0 ? `${count} ${count === 1 ? 'post' : 'posts'}` : series.status === 'live' ? '—' : STATUS_LABEL[series.status]}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
