import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import type { ReactNode } from 'react';
import { baseOptions } from '@/app/layout.config';
import { source } from '@/lib/source';

// One sidebar, every section visible at once, in reading order. The sections
// used to be root folders behind a tab switcher: the sidebar showed only the
// section you were in, the other seven sat in a dropdown most readers never
// opened, and Prev/Next stopped at the section boundary -- so finishing
// Overview left you with nowhere to go. Now the section order in
// content/docs/meta.json is also the Prev/Next order, and only the section
// you are reading is expanded (defaultOpenLevel 0), the way a classic
// Docusaurus sidebar behaves.
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <DocsLayout
      tree={source.pageTree}
      sidebar={{ tabs: false, defaultOpenLevel: 0 }}
      {...baseOptions}
    >
      {children}
    </DocsLayout>
  );
}
