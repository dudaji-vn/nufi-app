// A post's explainer video: no autoplay, nothing loads until the reader presses play.
export function PostVideo({ src, poster, caption }: { src: string; poster: string; caption: string }) {
  return (
    <figure className="post-video">
      <video controls preload="none" playsInline poster={poster} src={src} />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
