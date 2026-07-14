import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import type { ReactNode } from 'react';
import {
  BookMarked,
  Code,
  Compass,
  MessageSquare,
  Rocket,
  SlidersHorizontal,
} from 'lucide-react';
import { baseOptions } from '@/app/layout.config';
import { source } from '@/lib/source';

// One tab per top-level area. Every docs page belongs to a tab, so the
// switcher is present and consistent on every page (no orphan sections).
const personaTabs = [
  {
    title: 'Overview',
    description: 'What NUFI is',
    url: '/docs/overview',
    icon: <Compass />,
  },
  {
    title: 'Using the app',
    description: 'For everyday users',
    url: '/docs/end-user',
    icon: <MessageSquare />,
  },
  {
    title: 'Administer',
    description: 'Configure & manage',
    url: '/docs/admin',
    icon: <SlidersHorizontal />,
  },
  {
    title: 'Deploy & operate',
    description: 'Run the infrastructure',
    url: '/docs/deployment',
    icon: <Rocket />,
  },
  {
    title: 'Develop',
    description: 'Build & extend',
    url: '/docs/developer',
    icon: <Code />,
  },
  {
    title: 'Reference',
    description: 'Tables & glossary',
    url: '/docs/reference',
    icon: <BookMarked />,
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
