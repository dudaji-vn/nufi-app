import { docs } from '@/.source';
import { loader } from 'fumadocs-core/source';

const mdxSource = docs.toFumadocsSource();

export const source = loader({
  baseUrl: '/docs',
  source: {
    files:
      typeof mdxSource.files === 'function'
        ? (mdxSource.files as unknown as () => unknown[])()
        : mdxSource.files,
  } as Parameters<typeof loader>[0]['source'],
});
