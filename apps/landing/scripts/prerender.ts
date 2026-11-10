// After `vite build`: render every route to real HTML so crawlers and LLM fetchers (which don't run JavaScript)
// can read the site, and write the files they look for. Run by `bun run build`.
//   dist/<route>/index.html   each page, with its own title / description / canonical (+ article data for posts)
//   dist/blog/<slug>.md       each post as markdown
//   dist/llms.txt, dist/sitemap.xml, dist/robots.txt
//   dist/404.html             the app shell for unknown paths (served with status 404, noindex)
//
//   bun scripts/prerender.ts [distDir]     (default: ./dist)
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

// Bun 1.3.x can't load react-dom/server's production CommonJS build ("Expected CommonJS module to have a function
// wrapper"), and the Docker build runs with NODE_ENV=production. The development build renders the same HTML.
// React reads NODE_ENV when it is first loaded, so set it before the dynamic imports below.
process.env.NODE_ENV = 'development';
const { render } = await import('../src/entry-server');
const { POSTS } = await import('../src/posts/registry');
const { injectPage, pages } = await import('../src/seo');
const { extractArticle, llmsTxt, postMarkdown, robotsTxt, sitemapXml } = await import('../src/seo-build');

const DIST = resolve(process.argv[2] ?? join(import.meta.dir, '..', 'dist'));
const write = (rel: string, body: string) => {
  const p = join(DIST, rel);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, body);
};

const template = readFileSync(join(DIST, 'index.html'), 'utf8');
write('404.html', template.replace('<meta charset="UTF-8" />', '<meta charset="UTF-8" />\n    <meta name="robots" content="noindex" />'));

for (const page of pages()) {
  const html = await render(page.path);
  write(page.path === '/' ? 'index.html' : `${page.path.slice(1)}/index.html`, injectPage(template, page, html));
  if (page.post) write(`blog/${page.post.slug}.md`, postMarkdown(page.post, extractArticle(html)));
}

write('llms.txt', llmsTxt(POSTS));
write('sitemap.xml', sitemapXml(pages()));
write('robots.txt', robotsTxt());
console.log(`prerendered ${pages().length} pages, ${POSTS.length} markdown posts, llms.txt, sitemap.xml, robots.txt`);
