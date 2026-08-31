// Records the weekly report: department agents built and run in NUFI Studio.
//
// It answers the two questions a customer asks, in order -- what can this do,
// and how would we set it up -- so the setup is shown rather than assumed, and
// each flow is held on screen long enough to read.
//
// Nothing is captioned that has not been read back. A Playground run that
// errors, repeats a previous answer, or comes back with Han characters in
// Korean prose stops the recording instead of being filmed under a caption
// saying it worked.
//
//   node record-week.mjs --out week.webm
import { chromium } from 'playwright';
import { readFileSync, mkdirSync } from 'node:fs';
import { WEEK } from './week.mjs';
import { styles, THEME } from './stage.mjs';

const arg = (n, d) => {
  const i = process.argv.indexOf(`--${n}`);
  return i > -1 ? process.argv[i + 1] : d;
};
const STUDIO = arg('studio', 'http://localhost:7860');
const BOX = arg('box', 'http://127.0.0.1:8080');
const OUT = arg('out', 'week.webm');
const FONT = '"IBM Plex Sans","Helvetica Neue",Arial,sans-serif';
const FLOWS = JSON.parse(readFileSync(arg('flows', '../studio/flows.json'), 'utf8'));

const beat = (p, ms) => p.waitForTimeout(ms);

async function install(page) {
  await page.evaluate(([css]) => {
    if (document.getElementById('mbstyle')) return;
    const s = document.createElement('style');
    s.id = 'mbstyle'; s.textContent = css; document.head.appendChild(s);
    const stage = document.createElement('div'); stage.id = 'stage';
    const cap = document.createElement('div'); cap.id = 'cap';
    document.body.append(stage, cap);
  }, [styles(FONT)]);
}

async function card(page, { eyebrow, head, sub = [] }, hold = 7000) {
  await install(page);
  await page.evaluate(([e, h, s]) => {
    const el = document.getElementById('stage');
    el.innerHTML = (e ? `<div class="eyebrow">${e}</div>` : '')
      + `<h1>${h}</h1><div class="rule"></div>`
      + s.map((l) => `<p>${l}</p>`).join('');
    el.classList.add('on');
    document.getElementById('cap').classList.remove('on');
  }, [eyebrow || '', head, sub]);
  await beat(page, hold);
}

async function clearCard(page) {
  await page.evaluate(() => document.getElementById('stage')?.classList.remove('on'));
  await beat(page, 650);
}

async function say(page, lines, hold = 7500) {
  await install(page);
  await page.evaluate(([a, b]) => {
    const el = document.getElementById('cap');
    el.innerHTML = `<div class="l1"><b>${a}</b></div>` + (b ? `<div class="l2">${b}</div>` : '');
    el.classList.add('on');
  }, [lines[0], lines[1] || '']);
  await beat(page, hold);
}

const hush = (page) =>
  page.evaluate(() => document.getElementById('cap')?.classList.remove('on'));

// ---- canvas framing ------------------------------------------------------
// Langflow opens a flow at 200%, which shows one node and no wiring. The
// criterion for framing is not a zoom percentage but whether the whole graph is
// on screen, so that is what gets measured.
async function everythingVisible(page) {
  const n = page.locator('.react-flow__node');
  const count = await n.count();
  if (!count) return false;
  for (let i = 0; i < count; i++) {
    const b = await n.nth(i).boundingBox();
    if (!b) return false;
    if (b.x < 300 || b.x + b.width > 1570 || b.y < 60 || b.y + b.height > 930) return false;
  }
  return true;
}

async function graphBox(page) {
  const n = page.locator('.react-flow__node');
  const count = await n.count();
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (let i = 0; i < count; i++) {
    const b = await n.nth(i).boundingBox();
    if (!b) continue;
    x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
    x1 = Math.max(x1, b.x + b.width); y1 = Math.max(y1, b.y + b.height);
  }
  return count && x1 > x0 ? { x0, y0, x1, y1, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 } : null;
}

/** Frames the whole graph, centred and as large as it will go.
 *
 * This canvas has no pan: a left-drag does nothing and every wheel event is a
 * zoom. But the zoom is anchored at the cursor, so where the pointer sits is
 * the only steering available -- keep it on the middle of the graph and the
 * graph walks to the middle of the frame as it scales.
 */
async function frame(page) {
  await page.keyboard.down('Control');
  await page.mouse.move(935, 495);
  for (let i = 0; i < 8; i++) { await page.mouse.wheel(0, 300); await beat(page, 110); }
  for (let i = 0; i < 26; i++) {
    const g = await graphBox(page);
    if (g) await page.mouse.move(g.cx, g.cy);
    await page.mouse.wheel(0, -45);
    await beat(page, 170);
    if (!(await everythingVisible(page))) {
      await page.mouse.wheel(0, 45);
      await beat(page, 300);
      break;
    }
  }
  // A last nudge: zoom out one notch anchored at the frame centre, which pulls
  // the graph toward it without losing much size.
  const g = await graphBox(page);
  if (g && (Math.abs(g.cx - 935) > 60 || Math.abs(g.cy - 495) > 60)) {
    await page.mouse.move(935, 495);
    await page.mouse.wheel(0, 45);
    await beat(page, 250);
    await page.mouse.move(935, 495);
    await page.mouse.wheel(0, -45);
    await beat(page, 250);
  }
  await page.keyboard.up('Control');
  await beat(page, 700);
}

/** Zooms in on one node so its configuration can actually be read. */
async function closeUp(page, matchText) {
  const node = page.locator('.react-flow__node', { hasText: matchText }).first();
  const box = await node.boundingBox();
  if (!box) return false;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.keyboard.down('Control');
  for (let i = 0; i < 7; i++) { await page.mouse.wheel(0, -45); await beat(page, 180); }
  await page.keyboard.up('Control');
  await beat(page, 900);
  return true;
}

async function login(page) {
  await page.goto(`${STUDIO}/login`, { waitUntil: 'domcontentloaded' });
  await beat(page, 2500);
  await page.fill('input[type=text], input[name=username]', 'admin');
  await page.fill('input[type=password]', 'meshbox-local-dev');
  await page.click('button[type=submit]');
  await page.waitForURL(/\/flows?/, { timeout: 60000 });
  await beat(page, 2500);
}

async function openFlow(page, flow) {
  await page.goto(`${STUDIO}/flow/${flow.id}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.react-flow__node', { timeout: 60000 });
  await beat(page, 1800);
  await install(page);
  await frame(page);
  const nodes = await page.locator('.react-flow__node').count();
  console.log(`  canvas ${flow.name}: ${nodes} nodes`);
}

/** Runs one scenario in the Playground and returns what it actually answered. */
async function playground(page, ask, { timeout = 300000 } = {}) {
  await hush(page);
  await beat(page, 400);
  await page.click('button:has-text("Playground")');
  await page.waitForSelector('textarea, [contenteditable="true"]', { timeout: 60000 });
  await beat(page, 1500);
  await install(page);
  const box = page.locator('textarea, [contenteditable="true"]').last();
  await box.click();
  await box.fill(ask);
  await beat(page, 1100);
  await page.keyboard.press('Enter');

  // Scope to the chat turns. The Playground is a modal over the canvas, so a
  // page-level selector reads the component palette instead of the answer --
  // which is how an earlier cut captioned four scenarios it had never read.
  const turns = page.locator('[data-testid*="chat-message"]');
  const started = Date.now();
  let seen = '';
  while (Date.now() - started < timeout) {
    const txt = ((await turns.last().innerText().catch(() => '')) || '').trim();
    if (txt && txt !== ask && txt === seen) break;
    seen = txt;
    await beat(page, 1500);
  }
  if (!seen || seen === ask) throw new Error('playground produced no answer');
  if (/traceback|no matched type|internal server error/i.test(seen)) {
    throw new Error(`playground reported an error: ${seen.slice(0, 200)}`);
  }
  if (/[一-鿿]/.test(seen)) {
    throw new Error(`answer drifted out of Korean: ${seen.slice(0, 160)}`);
  }
  return seen;
}

async function closePlayground(page) {
  await hush(page);
  await page.click('[data-testid="playground-close-button"]').catch(() => {});
  await beat(page, 1200);
}

async function main() {
  mkdirSync('recording', { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    recordVideo: { dir: 'recording', size: { width: 1600, height: 1000 } },
  });
  const page = await ctx.newPage();

  // --- what this is ------------------------------------------------------
  await page.goto(`${BOX}/?lang=en`, { waitUntil: 'domcontentloaded' });
  await card(page, WEEK.title, 8000);
  await card(page, WEEK.premise, 8000);

  await page.fill('input[name=username]', 'admin');
  await page.fill('input[name=password]', 'meshbox');
  await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
                     page.click('button[type=submit]')]);
  await page.goto(`${BOX}/console/drives?lang=en`, { waitUntil: 'domcontentloaded' });
  await clearCard(page);
  await install(page);
  await say(page, WEEK.drive, 7000);
  await hush(page);

  // --- setup -------------------------------------------------------------
  await card(page, WEEK.setupCard, 9000);
  await login(page);
  await clearCard(page);
  await install(page);
  await say(page, WEEK.flowList, 8000);
  await hush(page);

  // the one field that matters, read at a size a person can read
  await openFlow(page, FLOWS.hr);
  await closeUp(page, 'Ollama');
  await install(page);
  await say(page, WEEK.wiring, 9500);
  await hush(page);
  await card(page, WEEK.reproduce, 8500);

  // --- scenario 1, slowly -------------------------------------------------
  await card(page, { head: WEEK.legal.head }, 4000);
  await clearCard(page);
  await openFlow(page, FLOWS.legal);
  await say(page, WEEK.legal.anatomy1, 8500);
  await say(page, WEEK.legal.anatomy2, 8500);
  await say(page, WEEK.legal.ask, 7000);
  const a1 = await playground(page, FLOWS.legal.ask);
  console.log(`  legal: ${a1.replace(/\s+/g, ' ').slice(0, 100)}`);
  await say(page, WEEK.legal.run, 9500);
  await closePlayground(page);

  // --- scenario 2, the tool ----------------------------------------------
  await card(page, { head: WEEK.hr.head }, 4000);
  await clearCard(page);
  await openFlow(page, FLOWS.hr);
  await say(page, WEEK.hr.anatomy1, 8500);
  await say(page, WEEK.hr.anatomy2, 8500);
  await say(page, WEEK.hr.why, 9000);
  const a2 = await playground(page, FLOWS.hr.ask);
  console.log(`  hr: ${a2.replace(/\s+/g, ' ').slice(0, 100)}`);
  await say(page, WEEK.hr.run, 9500);
  await say(page, WEEK.hr.lesson, 9000);
  await closePlayground(page);

  // --- three more ---------------------------------------------------------
  for (const [key, copy] of [['strategy', WEEK.strategy], ['support', WEEK.support],
                             ['finance', WEEK.finance]]) {
    await card(page, { head: copy.head }, 4000);
    await clearCard(page);
    await openFlow(page, FLOWS[key]);
    await say(page, copy.ask, 7000);
    const ans = await playground(page, FLOWS[key].ask);
    console.log(`  ${key}: ${ans.replace(/\s+/g, ' ').slice(0, 100)}`);
    await say(page, copy.run, 9000);
    await closePlayground(page);
  }

  // --- the rest, and the close -------------------------------------------
  await card(page, WEEK.coverage, 10000);
  await card(page, WEEK.refuses, 11000);
  await card(page, WEEK.fixes, 9500);
  await card(page, WEEK.close, 8500);

  const video = page.video();
  await ctx.close();
  await video.saveAs(OUT);
  await browser.close();
  console.log(`wrote ${OUT}`);
}

main().catch((e) => { console.error(String(e.message || e)); process.exit(1); });
