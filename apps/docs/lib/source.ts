import { createElement } from 'react';
import { docs } from '@/.source';
import { loader } from 'fumadocs-core/source';
import * as lucide from 'lucide-react';

// fumadocs-mdx 11.x returns `files` as a lazy function, but fumadocs-core's
// loader (and the search indexer) expect a materialised array. Call it here,
// then cast back to the original source type so page data — including `body`,
// `toc`, etc. — stays fully typed for `app/docs/[[...slug]]/page.tsx`.
const mdxSource = docs.toFumadocsSource();

const files =
  typeof mdxSource.files === 'function'
    ? (mdxSource.files as unknown as () => unknown[])()
    : mdxSource.files;

export const source = loader({
  baseUrl: '/docs',
  source: { ...mdxSource, files } as typeof mdxSource,
  // Render meta.json `icon` strings (Lucide names) as real icons in the
  // sidebar tree and tabs. Without this, the raw name renders as text.
  icon(icon) {
    if (icon && icon in lucide) {
      return createElement(lucide[icon as keyof typeof lucide] as never);
    }
  },
});
