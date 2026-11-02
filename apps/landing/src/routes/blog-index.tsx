import { Link } from '@tanstack/react-router';
import { Icon } from '../components/icon';
import { PostCard } from '../components/post-card';
import { useHead } from '../components/head';
import { POSTS } from '../posts/registry';

export function BlogIndex() {
  useHead(
    'Blog — NuFi Box',
    'Use cases and field notes from a real NuFi Box: how it answers from your documents, runs air-gapped, and keeps everything on the box.',
  );
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
            {POSTS.map((post) => (
              <PostCard key={post.slug} post={post} />
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
