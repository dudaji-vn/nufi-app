import { Link, Navigate, useParams } from '@tanstack/react-router';
import { Icon } from '../components/icon';
import { useHead } from '../components/head';
import { postBySlug } from '../posts/registry';

export function BlogPost() {
  const { slug } = useParams({ strict: false }) as { slug?: string };
  const post = slug ? postBySlug(slug) : undefined;
  useHead(
    post ? `${post.title} — NuFi Box` : 'NuFi Box',
    post?.summary ?? 'Use cases and field notes from a real NuFi Box.',
  );
  if (!post) return <Navigate to="/blog" />;

  const Body = post.Body;
  return (
    <main>
      <div className="shell post-view">
        <article className="article">
          <Link className="back" to="/blog">
            <Icon name="arrow-l" /> All posts
          </Link>
          <Body />
        </article>
      </div>
    </main>
  );
}
