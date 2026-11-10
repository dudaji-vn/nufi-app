import { Navigate, useParams } from '@tanstack/react-router';
import { useHead } from '../components/head';
import { PostChrome } from '../components/blog/post-chrome';
import { postBySlug, type PostMeta } from '../posts/registry';
import { areaById } from '../posts/taxonomy';
import { BlogArea } from './blog-area';

// /blog/$slug serves both area pages (/blog/engineering) and posts. A test keeps slugs and area ids apart.
export function BlogPost() {
  const { slug } = useParams({ strict: false }) as { slug?: string };
  const area = slug ? areaById(slug) : undefined;
  if (area) return <BlogArea key={area.id} area={area} />;
  const post = slug ? postBySlug(slug) : undefined;
  if (!post) return <Navigate to="/blog" />;
  return <PostView key={post.slug} post={post} />;
}

function PostView({ post }: { post: PostMeta }) {
  useHead(`${post.title} — NuFi`, post.summary);
  const Body = post.Body;
  return (
    <main>
      <PostChrome post={post}>
        <Body />
      </PostChrome>
    </main>
  );
}
