import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from '@tanstack/react-router';
import { POSTS, type PostMeta } from '../../posts/registry';
import { adjacentInSeries, areaById, latest, postsInSeries, seriesOf } from '../../posts/taxonomy';
import { PostRow } from './post-row';

type Heading = { id: string; text: string };

const slugify = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');

// Breadcrumb + reading column + right rail ("On this page", "In this series") + "Keep reading".
export function PostChrome({ post, children }: { post: PostMeta; children: ReactNode }) {
  const area = areaById(post.area)!;
  const series = seriesOf(post);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [toc, setToc] = useState<Heading[]>([]);

  useEffect(() => {
    const hs = Array.from(bodyRef.current?.querySelectorAll('h2') ?? []);
    setToc(
      hs.map((h) => {
        if (!h.id) h.id = slugify(h.textContent ?? '');
        return { id: h.id, text: h.textContent ?? '' };
      }),
    );
  }, [post.slug]);

  const inSeries = postsInSeries(POSTS, post.area, post.series);
  const { prev, next } = adjacentInSeries(POSTS, post.slug);
  const more = [next, prev, ...latest(POSTS).filter((p) => p.series !== post.series || p.area !== post.area)]
    .filter((p): p is PostMeta => !!p && p.slug !== post.slug)
    .slice(0, 3);

  return (
    <div className="shell post-view">
      <div className="post-layout">
        <div className="post-col">
          <nav className="crumbs" aria-label="Breadcrumb">
            <Link to="/blog">Blog</Link>
            <span aria-hidden="true">›</span>
            <Link to="/blog/$slug" params={{ slug: area.id }}>
              {area.name}
            </Link>
            <span aria-hidden="true">›</span>
            <Link to="/blog/$slug" params={{ slug: area.id }} hash={series.id}>
              {series.name}
            </Link>
          </nav>
          <article className="article" ref={bodyRef}>
            {children}
          </article>
        </div>
        <aside className="post-rail" aria-label="In this post">
          {toc.length > 1 ? (
            <>
              <p className="lib-label">On this page</p>
              <ol className="rail-toc">
                {toc.map((h) => (
                  <li key={h.id}>
                    <a href={`#${h.id}`}>{h.text}</a>
                  </li>
                ))}
              </ol>
            </>
          ) : null}
          <p className="lib-label">In this series</p>
          <p className="rail-series">{series.name}</p>
          <ol className="rail-list">
            {inSeries.map((p) => (
              <li key={p.slug} aria-current={p.slug === post.slug ? 'page' : undefined}>
                <Link to="/blog/$slug" params={{ slug: p.slug }}>
                  {p.title}
                </Link>
              </li>
            ))}
          </ol>
        </aside>
      </div>
      {more.length ? (
        <section className="keep-reading" aria-labelledby="keep-h">
          <h2 id="keep-h" className="lib-label">
            Keep reading
          </h2>
          <div className="lib-grid">
            {more.map((p) => (
              <PostRow key={p.slug} post={p} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
