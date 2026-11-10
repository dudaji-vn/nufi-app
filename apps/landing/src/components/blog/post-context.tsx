import { createContext, useContext } from 'react';
import type { PostMeta } from '../../posts/registry';
import { formatDate } from '../../posts/taxonomy';

export const PostContext = createContext<PostMeta | null>(null);

// The meta line under a post's standfirst, from the post's registry entry (author · date · reading time).
export function PostByline() {
  const post = useContext(PostContext);
  if (!post) return null;
  return (
    <p className="byline">
      {post.author} · <time dateTime={post.date}>{formatDate(post.date)}</time> · {post.readingMinutes} min read
    </p>
  );
}
