import { Link } from '@tanstack/react-router';
import type { PostMeta } from '../../posts/registry';
import { formatDate, postPath } from '../../posts/taxonomy';

// One post in a text-first list. `lead` adds the post's own figure beside the text.
export function PostRow({ post, variant = 'row' }: { post: PostMeta; variant?: 'lead' | 'row' }) {
  const Figure = variant === 'lead' ? post.Figure : undefined;
  return (
    <article className={`lib-post lib-post--${variant}${Figure ? ' lib-post--fig' : ''}`}>
      <div className="lib-post__text">
        <p className="lib-path">{postPath(post)}</p>
        <h3>
          <Link to="/blog/$slug" params={{ slug: post.slug }}>
            {post.title}
          </Link>
        </h3>
        <p className="lib-post__sum">{post.summary}</p>
        <p className="lib-meta">
          <time dateTime={post.date}>{formatDate(post.date)}</time> · {post.readingMinutes} min read
          {post.video ? ' · ▶ video' : ''}
        </p>
      </div>
      {Figure ? (
        <Link to="/blog/$slug" params={{ slug: post.slug }} className="lib-post__fig" aria-hidden="true" tabIndex={-1}>
          <Figure />
        </Link>
      ) : null}
    </article>
  );
}
