import { Link } from '@tanstack/react-router';
import { Icon } from './icon';
import type { PostMeta } from '../posts/registry';

export function PostCard({ post }: { post: PostMeta }) {
  const Thumb = post.Thumb;
  return (
    <Link
      to="/blog/$slug"
      params={{ slug: post.slug }}
      className="post-card post-card--link"
      aria-label={`Read: ${post.title}`}
    >
      <div className="post-card__media" aria-hidden="true">
        {Thumb ? <Thumb /> : <img src={post.thumbSrc} alt={post.thumbAlt} loading="lazy" />}
      </div>
      <div className="post-card__body">
        <span className="post-card__kicker">{post.kicker}</span>
        <h3>{post.title}</h3>
        <p>{post.summary}</p>
        <span className="post-card__more">
          {post.cta} <Icon name="arrow" />
        </span>
      </div>
    </Link>
  );
}
