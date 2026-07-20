// Capture documentation screenshots from the live NUFI surfaces with Playwright.
//
//   bun run screenshots                # capture everything
//   bun run screenshots chat admin     # capture only the named surfaces
//
// Credentials are read from env vars — never hard-code them here:
//   NUFI_EMAIL=you@example.com NUFI_PASSWORD=… bun run screenshots
//
// Output lands in public/screenshots/ and is referenced from the MDX docs.

import { chromium } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdir } from 'node:fs/promises';

const __dirname = dirname(fileURLToPath(import.meta.url));
// Defaults to public/screenshots; override with NUFI_SHOT_DIR to test a run
// without overwriting the committed images.
const OUT_DIR = process.env.NUFI_SHOT_DIR || join(__dirname, '..', 'public', 'screenshots');

const EMAIL = process.env.NUFI_EMAIL;
const PASSWORD = process.env.NUFI_PASSWORD;

if (!EMAIL || !PASSWORD) {
  console.error(
    'Set NUFI_EMAIL and NUFI_PASSWORD before running, e.g.\n' +
      '  NUFI_EMAIL=you@example.com NUFI_PASSWORD=secret bun run screenshots',
  );
  process.exit(1);
}

const URLS = {
  chat: 'https://chat.nufi.me',
  admin: 'https://nufichat-admin-panel-production.up.railway.app',
  console: 'https://console.nufi.me',
};

// Which surfaces to run — defaults to all, or whatever is passed on the CLI.
const requested = process.argv.slice(2).filter((a) => a in URLS);
const surfaces = requested.length ? requested : Object.keys(URLS);

const VIEWPORT = { width: 1440, height: 900 };

/** Fill a login form generically, tolerating different markup per surface. */
async function login(page, baseUrl) {
  const email = page
    .locator('input[type="email"], input[name="email"], #email')
    .first();
  const password = page
    .locator('input[type="password"], input[name="password"], #password')
    .first();

  // Some surfaces land on a dashboard if a shared cookie already authed us.
  if (!(await email.isVisible({ timeout: 8000 }).catch(() => false))) {
    return false;
  }

  await email.fill(EMAIL);
  await password.fill(PASSWORD);
  await page
    .getByRole('button', { name: /sign in|log ?in|continue|submit/i })
    .first()
    .click()
    .catch(async () => {
      await page.locator('button[type="submit"]').first().click();
    });

  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(2500);
  return true;
}

async function shot(page, name) {
  const file = join(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  console.log(`  ✓ ${name}.png`);
}

/** Click a control by accessible name, screenshot the result, then close it. */
async function clickShot(page, name, file, { after = 1300, close = true } = {}) {
  try {
    await page.getByRole('button', { name }).first().click({ timeout: 8000 });
    await page.waitForTimeout(after);
    await shot(page, file);
    if (close) {
      await page.keyboard.press('Escape').catch(() => {});
      await page.waitForTimeout(400);
    }
  } catch (err) {
    console.error(`  ✗ ${file} skipped: ${err.message.split('\n')[0]}`);
  }
}

/** Collapse the chat-history sidebar for a cleaner, feature-focused shot. */
async function collapseSidebar(page) {
  const btn = page.getByRole('button', { name: /close sidebar/i });
  if (await btn.count()) {
    await btn.click().catch(() => {});
    await page.waitForTimeout(600);
  }
}

/**
 * Redact people's names and emails in team member/invite views so a
 * regenerated screenshot never leaks a real teammate's personal data.
 * Generic — it keys off email nodes, so it doesn't hard-code anyone.
 */
async function redactPeople(page) {
  await page.evaluate(() => {
    const emailRe = /[\w.+-]+@[\w.-]+\.\w{2,}/;
    const placeholders = [
      ['Alex Kim', 'alex@example.com'],
      ['Sam Lee', 'sam@example.com'],
      ['Jordan Diaz', 'jordan@example.com'],
      ['Riley Cho', 'riley@example.com'],
    ];
    const roleWords = new Set(['owner', 'admin', 'member']);
    // Find the smallest element wrapping each email — that's a person row.
    const rows = new Set();
    document.querySelectorAll('*').forEach((el) => {
      if (el.children.length === 0) return;
      const t = el.textContent || '';
      if (emailRe.test(t) && t.length < 120) rows.add(el);
    });
    let i = 0;
    for (const row of rows) {
      // Only rewrite the innermost matching row.
      if ([...row.querySelectorAll('*')].some((c) => rows.has(c))) continue;
      const [name, email] = placeholders[i % placeholders.length];
      i += 1;
      const walk = (node) => {
        if (node.nodeType === 3) {
          const v = node.nodeValue.trim();
          if (!v) return;
          if (emailRe.test(v)) node.nodeValue = email;
          else if (!roleWords.has(v.toLowerCase()) && v.length > 1) node.nodeValue = name;
        } else {
          node.childNodes.forEach(walk);
        }
      };
      walk(row);
    }
  });
}

/** Agent Builder — the knowledge (RAG / File Search) flow. */
async function captureKnowledgeAgent(page) {
  await page.getByRole('button', { name: /^agent builder$/i }).first().click().catch(() => {});
  await page.waitForTimeout(3500);
  // Give the sample knowledge file a neutral, illustrative name for the docs.
  await page.evaluate(() => {
    document.querySelectorAll('*').forEach((el) => {
      if (el.children.length) return;
      const t = (el.textContent || '').trim();
      if (/\.pdf$/i.test(t) && t.length < 60) el.textContent = 'Employee Handbook.pdf';
    });
  });
  await shot(page, 'chat-agent-knowledge');

  await page.getByRole('button', { name: /create new agent/i }).first().click().catch(() => {});
  await page.waitForTimeout(1800);
  // Scroll the builder drawer so the File Search capability is in view.
  await page.evaluate(() => {
    const label = [...document.querySelectorAll('*')].find(
      (e) => /Capabilities/.test(e.textContent) && e.children.length < 3,
    );
    let el = label;
    while (el) {
      const s = getComputedStyle(el);
      if ((s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
        el.scrollTop = el.scrollHeight;
        break;
      }
      el = el.parentElement;
    }
  });
  await page.waitForTimeout(1000);
  await shot(page, 'chat-agent-new');
}

/** Teams — the shared workspace: members, invites, sharing, groups. */
async function captureTeams(page) {
  await collapseSidebar(page);
  await page.getByRole('button', { name: /^teams$/i }).first().click().catch(() => {});
  await page.waitForURL('**/teams', { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(2500);
  await shot(page, 'chat-teams-list');

  await clickShot(page, /create team/i, 'chat-team-create');

  // Open the first team card, then walk its tabs.
  await page.locator('div', { hasText: /team/i }).last().click().catch(() => {});
  await page.waitForTimeout(2500);

  const tab = async (name) => {
    await page.getByRole('tab', { name, exact: true }).click().catch(() => {});
    await page.waitForTimeout(1600);
  };

  await tab('Members');
  await redactPeople(page);
  await shot(page, 'chat-team-members');

  await page.getByRole('button', { name: /invite member/i }).first().click().catch(() => {});
  await page.waitForTimeout(1300);
  await redactPeople(page);
  await shot(page, 'chat-team-invite');
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(500);

  await tab('Knowledge');
  await page.getByRole('button', { name: /add file/i }).first().click().catch(() => {});
  await page.waitForTimeout(1300);
  await shot(page, 'chat-team-knowledge');
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(500);

  await tab('Shared');
  await shot(page, 'chat-team-shared');

  await tab('Groups');
  await shot(page, 'chat-team-groups');
}

const captures = {
  async chat(context) {
    const page = await context.newPage();
    await page.goto(`${URLS.chat}/login`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await shot(page, 'chat-sign-in');

    await login(page, URLS.chat);
    await page.goto(URLS.chat, { waitUntil: 'domcontentloaded' });
    // Wait for the message composer to render so the shot shows a real UI.
    const composer = page.getByRole('textbox', { name: /message input/i }).first();
    await composer
      .waitFor({ timeout: 20000 })
      .catch(() => {});
    await page.waitForTimeout(4000);
    await shot(page, 'chat-home');

    // Feature menus, each opened from the composer / top bar / left rail.
    await clickShot(page, /select a model/i, 'chat-model-menu');
    await clickShot(page, /presets/i, 'chat-presets-menu');
    await clickShot(page, /attach file options/i, 'chat-attach-menu');
    await clickShot(page, /tools options/i, 'chat-tools-menu');
    await clickShot(page, /^parameters$/i, 'chat-parameters', { close: false });
    // The Parameters side panel stays open — toggle it shut for a clean shot.
    await page
      .getByRole('button', { name: /^parameters$/i })
      .first()
      .click()
      .catch(() => {});
    await page.waitForTimeout(800);

    // A real, completed conversation so docs can show what chatting looks like.
    try {
      await composer.click();
      await composer.fill(
        'In one friendly sentence, what can you help me with?',
      );
      await page.getByRole('button', { name: /send message/i }).first().click();
      // Wait for the assistant reply to finish streaming.
      await page.waitForTimeout(12000);
      await shot(page, 'chat-conversation');
    } catch (err) {
      console.error(`  ✗ chat-conversation skipped: ${err.message.split('\n')[0]}`);
    }

    // Left-rail panels referenced by the docs.
    await clickShot(page, /^skills$/i, 'chat-skills');
    await clickShot(page, /account settings/i, 'chat-account-menu');

    // Knowledge (RAG) and Teams surfaces.
    await captureKnowledgeAgent(page).catch((err) =>
      console.error(`  ✗ knowledge agent skipped: ${err.message.split('\n')[0]}`),
    );
    await captureTeams(page).catch((err) =>
      console.error(`  ✗ teams skipped: ${err.message.split('\n')[0]}`),
    );

    await page.close();
  },

  async admin(context) {
    const page = await context.newPage();
    await page.goto(URLS.admin, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    await shot(page, 'admin-sign-in');

    await login(page, URLS.admin);
    await page.waitForTimeout(3000);
    await shot(page, 'admin-home');

    // Each top-level section of the admin panel.
    const section = async (path, file, settle = 3000) => {
      await page.goto(URLS.admin + path, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(settle);
      await shot(page, file);
    };
    await section('/configuration', 'admin-configuration');
    await section('/access', 'admin-access');
    await section('/grants', 'admin-grants');

    // Access → open the ADMIN role to show the Details / Permissions / Members tabs.
    await page.goto(URLS.admin + '/access', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2500);
    await page.getByRole('button', { name: /^ADMIN/ }).first().click().catch(() => {});
    await page.waitForTimeout(1800);
    await shot(page, 'admin-role-detail');

    await page.close();
  },

  async console(context) {
    const page = await context.newPage();
    await page.goto(URLS.console, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);
    // Console shares the .nufi.me session cookie with the chat; log in if asked.
    await login(page, URLS.console).catch(() => {});
    await page.goto(URLS.console, { waitUntil: 'domcontentloaded' });
    // Wait for the skeleton loaders to resolve into real content.
    await page
      .getByText(/profile|api key|usage|budget/i)
      .first()
      .waitFor({ timeout: 15000 })
      .catch(() => {});
    await page.waitForTimeout(4000);
    await shot(page, 'console-home');
    await page.close();
  },
};

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
  });

  for (const surface of surfaces) {
    console.log(`\n▶ ${surface} (${URLS[surface]})`);
    try {
      await captures[surface](context);
    } catch (err) {
      console.error(`  ✗ ${surface} failed: ${err.message}`);
    }
  }

  await browser.close();
  console.log(`\nDone. Screenshots in public/screenshots/`);
}

// Exported for focused testing; only auto-runs when invoked directly.
export { login, shot, redactPeople, captureTeams, captureKnowledgeAgent, VIEWPORT, URLS };

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
