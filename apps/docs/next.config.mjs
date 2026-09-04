import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,

  // The NUFI Works pages used to live under /docs/end-user. They were listed
  // in the Works sidebar by cross-reference, which rendered fine but kept the
  // canonical URL in the chat section -- so clicking "Assigning work to
  // agents" from the Works sidebar threw you into the "Using the app" tab.
  // They now live in /docs/works. These keep the old addresses working for
  // anything already linked or bookmarked.
  async redirects() {
    return [
      { source: '/docs/end-user/agent-tasks', destination: '/docs/works/tasks', permanent: true },
      { source: '/docs/end-user/agent-approvals', destination: '/docs/works/approvals', permanent: true },
      { source: '/docs/end-user/agent-connect', destination: '/docs/works/connect-account', permanent: true },
      // The short Studio page duplicated the Studio section it linked to.
      { source: '/docs/end-user/studio', destination: '/docs/studio', permanent: true },

      // Same shape, milder symptom: /docs/operations and /docs/getting-started
      // were page pools with no tab of their own, referenced by exactly one
      // section each. Landing on one kept the section's page list but dropped
      // the tab switcher, so the control for changing section vanished on a
      // handful of pages and came back on the rest. They now live in the
      // section that owned them.
      { source: '/docs/operations/troubleshooting', destination: '/docs/deployment/troubleshooting', permanent: true },
      { source: '/docs/operations/upgrade-librechat', destination: '/docs/deployment/upgrade-librechat', permanent: true },
      { source: '/docs/operations/faq', destination: '/docs/deployment/faq', permanent: true },
      { source: '/docs/operations', destination: '/docs/deployment', permanent: true },
      { source: '/docs/getting-started/prerequisites', destination: '/docs/developer/prerequisites', permanent: true },
      { source: '/docs/getting-started/quick-start', destination: '/docs/developer/quick-start', permanent: true },
      { source: '/docs/getting-started/verify-install', destination: '/docs/developer/verify-install', permanent: true },
      { source: '/docs/getting-started', destination: '/docs/developer', permanent: true },

      // A design note on RAG paths sat at the end of Overview. Once Prev/Next
      // runs across sections it was the last thing a new reader met before
      // "Using the app"; it belongs with the other engineering notes.
      { source: '/docs/overview/rag-integration', destination: '/docs/developer/rag-integration', permanent: true },
    ];
  },
};

export default withMDX(config);
