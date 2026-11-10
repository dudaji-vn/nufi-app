import { describe, expect, test } from 'bun:test';
import { POSTS } from './posts/registry';
import { AREAS } from './posts/taxonomy';
import { SITE, headTags, injectPage, pages } from './seo';
import { extractArticle, llmsTxt, postMarkdown, robotsTxt, sitemapXml } from './seo-build';
import { render } from './entry-server';

const TEMPLATE = `<html><head><meta charset="UTF-8" />
<title>Old</title>
<meta name="description" content="old" />
<link rel="canonical" href="https://box.nufi.me/" />
</head><body><div id="root"></div><script type="module" src="/assets/x.js"></script></body></html>`;

const post = POSTS[0]!;

describe('pages', () => {
  test('every route is listed once: home, blog, each area, each post', () => {
    const paths = pages().map((p) => p.path);
    expect(paths).toEqual(['/', '/blog', ...AREAS.map((a) => `/blog/${a.id}`), ...POSTS.map((p) => `/blog/${p.slug}`)]);
  });
});

describe('headTags', () => {
  test('a post gets its own title, description, canonical, article type and markdown alternate', () => {
    const h = pages().find((p) => p.path === `/blog/${post.slug}`)!;
    const tags = headTags(h);
    expect(tags).toContain(`<title>${post.title} — NuFi</title>`);
    expect(tags).toContain(`<link rel="canonical" href="${SITE}/blog/${post.slug}" />`);
    expect(tags).toContain('<meta property="og:type" content="article" />');
    expect(tags).toContain(`<link rel="alternate" type="text/markdown" href="/blog/${post.slug}.md" />`);
    const ld = JSON.parse(/<script type="application\/ld\+json">(.*?)<\/script>/s.exec(tags)![1]!);
    expect(ld).toMatchObject({ '@type': 'BlogPosting', headline: post.title, datePublished: post.date,
      author: { name: post.author } });
  });

  test('text is HTML-escaped', () => {
    const tags = headTags({ path: '/x', title: 'A & "B" <c>', description: "it's", type: 'website' });
    expect(tags).toContain('<title>A &amp; &quot;B&quot; &lt;c&gt;</title>');
    expect(tags).not.toContain('<c>');
  });
});

describe('injectPage', () => {
  test('replaces the static head block and fills #root', () => {
    const out = injectPage(TEMPLATE, { path: '/blog', title: 'Blog — NuFi', description: 'd', type: 'website' },
      '<main>hi</main>');
    expect(out).toContain('<title>Blog — NuFi</title>');
    expect(out).not.toContain('<title>Old</title>');
    expect(out).not.toContain('href="https://box.nufi.me/"');
    expect(out).toContain('<div id="root"><main>hi</main></div>');
    expect(out).toContain('<meta charset="UTF-8" />');
    expect(out).toContain('src="/assets/x.js"');
  });

  test('fails loudly if the template changed shape', () => {
    expect(() => injectPage('<html></html>', pages()[0]!, 'x')).toThrow();
  });
});

describe('render (what crawlers and LLMs get)', () => {
  for (const p of POSTS) {
    test(`post ${p.slug} renders its title and article text`, async () => {
      const html = await render(`/blog/${p.slug}`);
      expect(html).toContain(p.title.replace(/'/g, '&#x27;'));
      const article = extractArticle(html);
      expect(article.replace(/<[^>]+>/g, '').length).toBeGreaterThan(1500);
    });
  }

  test('home and blog index render real content', async () => {
    expect(await render('/')).toContain('Private AI for teams');
    for (const p of POSTS) expect(await render('/blog')).toContain(`/blog/${p.slug}`);
  });
});

describe('markdown copy', () => {
  test('has the title, byline, canonical, and absolute links', async () => {
    const md = postMarkdown(post, extractArticle(await render(`/blog/${post.slug}`)));
    expect(md.startsWith(`# ${post.title}\n`)).toBe(true);
    expect(md).toContain(`By ${post.author} · ${post.date}`);
    expect(md).toContain(`${SITE}/blog/${post.slug}`);
    expect(md).toContain('## ');
    expect(md).not.toMatch(/\]\(\/(?!\/)/); // no site-relative links left
    expect(md).not.toContain('<div');
  });
});

test('each post states its title and byline once (the body header is not repeated)', async () => {
  for (const p of POSTS) {
    const md = postMarkdown(p, extractArticle(await render(`/blog/${p.slug}`)));
    expect(md.split('\n').filter((l) => l === `# ${p.title}`).length).toBe(1);
    expect(md.match(/min read/g)?.length).toBe(1);
    expect(md).not.toContain(`${p.author} · ${p.date.replace(/-/g, '.')}`);
  }
});

describe('crawler files', () => {
  test('llms.txt lists every post with its markdown link, newest first', () => {
    const txt = llmsTxt(POSTS);
    expect(txt.startsWith('# NuFi')).toBe(true);
    for (const p of POSTS) expect(txt).toContain(`[${p.title}](${SITE}/blog/${p.slug}.md)`);
    expect(txt.indexOf(POSTS[0]!.title)).toBeLessThan(txt.indexOf(POSTS[1]!.title));
  });

  test('sitemap lists every page with absolute URLs', () => {
    const xml = sitemapXml(pages());
    for (const p of pages()) expect(xml).toContain(`<loc>${SITE}${p.path === '/' ? '/' : p.path}</loc>`);
    expect(xml).toContain(`<lastmod>${post.date}</lastmod>`);
  });

  test('robots allows everyone and points at the sitemap', () => {
    expect(robotsTxt()).toBe(`User-agent: *\nAllow: /\n\nSitemap: ${SITE}/sitemap.xml\n`);
  });
});

test('prerendered markup has no inline scripts', async () => {
  for (const p of pages()) expect(await render(p.path)).not.toContain('<script');
});
