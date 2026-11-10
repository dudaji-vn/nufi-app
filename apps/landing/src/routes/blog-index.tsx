import { useState } from 'react';
import { useHead } from '../components/head';
import { AreaFolder } from '../components/blog/area-folder';
import { PostRow } from '../components/blog/post-row';
import { POSTS } from '../posts/registry';
import { AREAS, latest, type AreaId } from '../posts/taxonomy';

export function BlogIndex() {
  useHead(
    'Blog — NuFi',
    'Engineering notes on AI-native data platforms for factories, and field notes from the NuFi Box private AI appliance.',
  );
  const [filter, setFilter] = useState<AreaId | 'all'>('all');
  const posts = latest(POSTS).filter((p) => filter === 'all' || p.area === filter);
  const [lead, ...rest] = posts;

  return (
    <main className="lib">
      <section className="shell lib-hd">
        <p className="lib-label">Blog · {POSTS.length} posts</p>
        <h1>
          We build private AI that runs on your own hardware, and we write about how factories can run their data
          platforms on AI.
        </h1>
      </section>

      <section className="shell lib-areas" aria-label="Areas">
        {AREAS.map((area, i) => (
          <AreaFolder key={area.id} area={area} posts={POSTS} index={i} />
        ))}
      </section>

      <section className="shell lib-latest" aria-labelledby="latest-h">
        <div className="lib-latest__hd">
          <h2 id="latest-h" className="lib-label">
            Latest
          </h2>
          <div className="lib-filter" role="group" aria-label="Filter by area">
            {(['all', ...AREAS.map((a) => a.id)] as const).map((id) => (
              <button
                key={id}
                type="button"
                aria-pressed={filter === id}
                className={filter === id ? 'is-on' : undefined}
                onClick={() => setFilter(id)}
              >
                {id === 'all' ? 'All' : AREAS.find((a) => a.id === id)!.name}
              </button>
            ))}
          </div>
        </div>
        {lead ? <PostRow post={lead} variant="lead" /> : null}
        <div className="lib-grid">
          {rest.map((p) => (
            <PostRow key={p.slug} post={p} />
          ))}
        </div>
      </section>
    </main>
  );
}
