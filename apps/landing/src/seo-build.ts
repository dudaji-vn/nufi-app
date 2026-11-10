import TurndownService from 'turndown';
import { POSTS, type PostMeta } from './posts/registry';
import { AREAS, latest } from './posts/taxonomy';
import { SITE, type PageHead } from './seo';

// Build-only (scripts/prerender.ts): what crawlers and LLM fetchers get besides the prerendered pages —
// a markdown copy of each post, /llms.txt, /sitemap.xml and /robots.txt. Never imported by the client bundle.

// The post body as rendered inside <article class="article">…</article> (PostChrome).
export function extractArticle(html: string): string {
  const open = /<article class="article"[^>]*>/.exec(html);
  if (!open) throw new Error('no <article class="article"> in rendered page');
  let depth = 1;
  const tag = /<(\/?)article\b[^>]*>/g;
  tag.lastIndex = open.index + open[0].length;
  for (let m = tag.exec(html); m; m = tag.exec(html)) {
    depth += m[1] ? -1 : 1;
    if (depth === 0) return html.slice(open.index + open[0].length, m.index);
  }
  throw new Error('unclosed <article>');
}

const absolute = (url: string) => (url.startsWith('/') && !url.startsWith('//') ? SITE + url : url);

function turndown(): TurndownService {
  const td = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced', bulletListMarker: '-' });
  td.addRule('video', {
    filter: 'video',
    replacement: (_c, node) => {
      const el = node as HTMLElement;
      const src = el.getAttribute('src') ?? el.querySelector('source')?.getAttribute('src') ?? '';
      return src ? `\n\n[Video](${absolute(src)})\n\n` : '';
    },
  });
  td.remove((node) => ['SCRIPT', 'STYLE', 'SVG', 'BUTTON'].includes(node.nodeName.toUpperCase()));
  return td;
}

// Drop the body's own header (area label, H1, byline line): the markdown header below states those once.
function stripBodyHeader(md: string, p: PostMeta): string {
  const h1 = md.indexOf(`# ${p.title}\n`);
  const afterH1 = h1 >= 0 ? md.slice(h1 + p.title.length + 3) : md;
  const byline = new RegExp(`^.*· ${p.date.replace(/-/g, '\\.')} · \\d+ min read\\s*$`, 'm');
  return afterH1.replace(byline, '');
}

export function postMarkdown(p: PostMeta, articleHtml: string): string {
  const body = turndown()
    .turndown(articleHtml)
    .replace(/\]\((\/[^)\s]*)/g, (_m, u: string) => `](${absolute(u)}`);
  return [
    `# ${p.title}`,
    '',
    `By ${p.author} · ${p.date} · ${p.readingMinutes} min read`,
    `Source: ${SITE}/blog/${p.slug}`,
    '',
    stripBodyHeader(body, p).replace(/\n{3,}/g, '\n\n').trim(),
    '',
  ].join('\n');
}

export function llmsTxt(posts: PostMeta[]): string {
  const lines = [
    '# NuFi',
    '',
    '> NuFi Box is a small on-premise AI appliance: a private chat that answers from your documents, on your GPU, on your network. The blog has engineering notes on AI-native data platforms and field notes from the box.',
    '',
    `Every post is also available as markdown (the links below). Site: ${SITE}`,
    '',
  ];
  for (const area of AREAS) {
    const inArea = latest(posts).filter((p) => p.area === area.id);
    if (!inArea.length) continue;
    lines.push(`## ${area.name}`, '');
    for (const p of inArea) lines.push(`- [${p.title}](${SITE}/blog/${p.slug}.md): ${p.summary}`);
    lines.push('');
  }
  return lines.join('\n');
}

export function sitemapXml(all: PageHead[]): string {
  const newest = latest(POSTS)[0]?.date;
  const urls = all.map((h) => {
    const lastmod = h.post?.date ?? newest;
    return `  <url><loc>${SITE}${h.path}</loc>${lastmod ? `<lastmod>${lastmod}</lastmod>` : ''}</url>`;
  });
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>\n`;
}

export const robotsTxt = () => `User-agent: *\nAllow: /\n\nSitemap: ${SITE}/sitemap.xml\n`;
