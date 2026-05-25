import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import type { ReactNode } from 'react';
import { baseOptions } from '@/app/layout.config';
import { source } from '@/lib/source';

const personaTabs = [
  {
    title: 'Overview',
    description: 'Start here',
    url: '/docs/overview',
  },
  {
    title: 'End user',
    description: 'Chat + console',
    url: '/docs/end-user',
  },
  {
    title: 'Admin',
    description: 'Configure & manage',
    url: '/docs/admin',
  },
  {
    title: 'Developer',
    description: 'Run & ship locally',
    url: '/docs/developer',
  },
  {
    title: 'DevOps',
    description: 'Deploy & operate',
    url: '/docs/deployment',
  },
  {
    title: 'Reference',
    description: 'Tables & glossary',
    url: '/docs/reference',
  },
];

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <DocsLayout
      tree={source.pageTree}
      sidebar={{ tabs: personaTabs }}
      {...baseOptions}
    >
      {children}
    </DocsLayout>
  );
}
