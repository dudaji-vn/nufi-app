// Navigation checks for the docs site. Run against a served build:
//
//   bun run build && bun run start -p 3123 &
//   node scripts/check-nav.mjs http://localhost:3123
//
// These guard the sidebar model chosen in PR #60: one tree, every section
// visible, Prev/Next running across sections, section headers linking to
// their intro page. Each check names the regression it would catch.
import { chromium } from '@playwright/test';

const base = (process.argv[2] ?? 'http://localhost:3000').replace(/\/$/, '');

// Every top-level section, in the order content/docs/meta.json lists them.
const SECTIONS = [
  'Overview',
  'Using the app',
  'NUFI Studio',
  'NUFI Works',
  'Administer',
  'Deploy & operate',
  'Develop',
  'Reference',
];

// Pages the checks navigate to. Keep these pointing at pages that exist; a
// moved page shows up here as a failed check, which is the point.
const PAGES = {
  nested: '/docs/overview/architecture', // a page inside a section
  nestedSection: '/docs/overview', // its section intro
  lastOfFirstSection: '/docs/overview/security', // last page of Overview
  firstOfSecondSection: '/docs/end-user', // intro of Using the app
  redirectedFrom: '/docs/overview/rag-integration', // moved in PR #60
  redirectedTo: '/docs/developer/rag-integration',
  deepInSection: '/docs/works/tasks',
  deepSectionLabel: 'NUFI Works',
  deepSectionIntro: '/docs/works',
};

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  -- ${detail}` : ''}`);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const go = (p) => page.goto(base + p, { waitUntil: 'networkidle', timeout: 60000 });
const lastDocLinks = () =>
  page
    .locator('article a[href^="/docs/"], main a[href^="/docs/"]')
    .evaluateAll((as) => as.slice(-4).map((a) => a.getAttribute('href')));

// 1. Every section is visible in the sidebar at once, from any page.
await go(PAGES.nested);
const sidebarText = await page.locator('aside').first().innerText();
const missing = SECTIONS.filter((s) => !sidebarText.includes(s));
check(
  'sidebar lists every section on a nested page',
  missing.length === 0,
  missing.length ? `missing: ${missing.join(', ')}` : '',
);

// 2. No root-toggle dropdown hiding the sections (the pre-#60 tab switcher).
const dropdown = await page.locator('aside button[aria-haspopup]').count();
check('no section dropdown in the sidebar', dropdown === 0, `found ${dropdown}`);

// 3. Breadcrumb: a link to the section, rendered above the H1.
const h1Box = await page.locator('article h1').first().boundingBox();
const crumb = page.locator(`article a[href="${PAGES.nestedSection}"]`).first();
const crumbBox = (await crumb.count()) ? await crumb.boundingBox() : null;
check(
  'breadcrumb links to the section above the title',
  Boolean(crumbBox && h1Box && crumbBox.y < h1Box.y),
  crumbBox ? `crumb y=${Math.round(crumbBox.y)} h1 y=${Math.round(h1Box?.y ?? -1)}` : 'no link found',
);

// 4. Next from the last page of the first section crosses into the second.
await go(PAGES.lastOfFirstSection);
const nextLinks = await lastDocLinks();
check(
  `Next from ${PAGES.lastOfFirstSection} reaches ${PAGES.firstOfSecondSection}`,
  nextLinks.some((h) => h === PAGES.firstOfSecondSection || h.startsWith(`${PAGES.firstOfSecondSection}/`)),
  nextLinks.join(' '),
);

// 5. A moved page keeps its old address.
const resp = await page.request.get(base + PAGES.redirectedFrom, { maxRedirects: 0 });
const loc = resp.headers().location ?? '';
check(
  `${PAGES.redirectedFrom} redirects to ${PAGES.redirectedTo}`,
  [301, 308].includes(resp.status()) && loc.includes(PAGES.redirectedTo),
  `status ${resp.status()} location ${loc}`,
);
const r2 = await page.request.get(base + PAGES.redirectedTo);
check(`${PAGES.redirectedTo} renders`, r2.status() === 200, `status ${r2.status()}`);

// 6. Prev from the first page of the second section points back into the first.
await go(PAGES.firstOfSecondSection);
const prevLinks = await lastDocLinks();
check(
  `Prev from ${PAGES.firstOfSecondSection} points into ${PAGES.nestedSection}`,
  prevLinks.some((h) => h.startsWith(PAGES.nestedSection)),
  prevLinks.join(' '),
);

// 7. A section header is itself the link to the intro; the intro is not
//    repeated as a first child with the same label.
await go(PAGES.deepInSection);
const deepAside = await page.locator('aside').first().innerText();
const labelCount = (deepAside.match(new RegExp(PAGES.deepSectionLabel, 'g')) || []).length;
check(
  `section label "${PAGES.deepSectionLabel}" appears once in the sidebar`,
  labelCount === 1,
  `x${labelCount}`,
);
const headerLink = await page.locator(`aside a[href="${PAGES.deepSectionIntro}"]`).count();
check('section header links to the section intro', headerLink >= 1, `links: ${headerLink}`);

await browser.close();
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} passed`);
process.exit(failed ? 1 : 0);
