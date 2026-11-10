import { POSTS, type PostMeta } from './posts/registry';
import { AREAS } from './posts/taxonomy';

// Per-page head (title, description, canonical, article data), shared by the browser (useHead) and the build-time
// prerender. Kept light: it ships in the client bundle. Build-only helpers live in seo-build.ts.

// Preferred canonical domain for the site (independent of which host serves it).
export const SITE = 'https://box.nufi.me';

export type PageHead = {
  path: string;
  title: string;
  description: string;
  type: 'website' | 'article';
  post?: PostMeta;
};

export const HOME_HEAD = {
  title: 'NuFi Box — Private AI appliance',
  description:
    'NuFi Box is a small on-premise AI appliance that runs the whole AI stack on your own hardware — a private chat that answers from your documents, on your GPU, on your network. Nothing leaves the box.',
};

export const BLOG_HEAD = {
  title: 'Blog — NuFi',
  description:
    'Engineering notes on AI-native data platforms for factories, and field notes from the NuFi Box private AI appliance.',
};

export const postHead = (p: PostMeta) => ({ title: `${p.title} — NuFi`, description: p.summary });
export const areaHead = (a: (typeof AREAS)[number]) => ({ title: `${a.name} — NuFi blog`, description: a.intro });

export function pages(): PageHead[] {
  return [
    { path: '/', type: 'website', ...HOME_HEAD },
    { path: '/blog', type: 'website', ...BLOG_HEAD },
    ...AREAS.map((a): PageHead => ({ path: `/blog/${a.id}`, type: 'website', ...areaHead(a) })),
    ...POSTS.map((p): PageHead => ({ path: `/blog/${p.slug}`, type: 'article', post: p, ...postHead(p) })),
  ];
}

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function headTags(h: PageHead): string {
  const url = SITE + h.path;
  const image = h.post?.video ? SITE + h.post.video.poster : `${SITE}/og.png`;
  const tags = [
    `<title>${esc(h.title)}</title>`,
    `<meta name="description" content="${esc(h.description)}" />`,
    `<meta property="og:title" content="${esc(h.title)}" />`,
    `<meta property="og:description" content="${esc(h.description)}" />`,
    `<meta property="og:type" content="${h.type}" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:image" content="${image}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${esc(h.title)}" />`,
    `<meta name="twitter:description" content="${esc(h.description)}" />`,
    `<meta name="twitter:image" content="${image}" />`,
    `<link rel="canonical" href="${url}" />`,
  ];
  if (h.post) {
    const p = h.post;
    tags.push(
      `<meta property="article:published_time" content="${p.date}" />`,
      `<meta name="author" content="${esc(p.author)}" />`,
      `<link rel="alternate" type="text/markdown" href="/blog/${p.slug}.md" />`,
      `<script type="application/ld+json">${JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        headline: p.title,
        description: p.summary,
        datePublished: p.date,
        author: { '@type': 'Organization', name: p.author },
        publisher: { '@type': 'Organization', name: 'NuFi' },
        url,
        image,
      }).replace(/</g, '\\u003c')}</script>`,
    );
  }
  return tags.join('\n    ');
}

// index.html's static head block runs from <title> to the canonical link; both must stay in the template.
const HEAD_BLOCK = /<title>[\s\S]*?<link rel="canonical"[^>]*>/;
const ROOT = '<div id="root"></div>';

export function injectPage(template: string, h: PageHead, appHtml: string): string {
  if (!HEAD_BLOCK.test(template) || !template.includes(ROOT)) {
    throw new Error('index.html no longer has the <title>…canonical head block or an empty #root');
  }
  return template.replace(HEAD_BLOCK, () => headTags(h)).replace(ROOT, () => `<div id="root">${appHtml}</div>`);
}
