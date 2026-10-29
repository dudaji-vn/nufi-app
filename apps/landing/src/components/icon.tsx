// Monochrome icon from the sprite in <Sprite/>. Colour comes from `currentColor`
// (inherited), size from the surrounding CSS rule (`.btn .ico`, `.card__ico .ico`,
// …), so most call sites pass only `name`. Pass `size` + an empty `className`
// for a one-off sized icon that isn't inside a styled icon context.
export function Icon({
  name,
  size,
  className = 'ico',
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  const dims = size ? { width: size, height: size } : {};
  return (
    <svg className={className || undefined} aria-hidden="true" {...dims}>
      <use href={`#i-${name}`} />
    </svg>
  );
}
