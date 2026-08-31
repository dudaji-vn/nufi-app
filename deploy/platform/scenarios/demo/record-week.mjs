// Records the weekly report: department agent scenarios, built and run in NUFI
// Studio, on the box.
//
// The discipline from the earlier cuts carries over. A caption is only written
// over an answer the recorder has read back; a Playground run that errors, or
// comes back with Han characters in Korean prose, stops the recording rather
// than being filmed under a caption saying it worked.
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

async function card(page, { eyebrow, head, sub = [] }, hold = 6500) {
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
  await beat(page, 600);
}

async function say(page, lines, hold = 6200) {
  await install(page);
  await page.evaluate(([a, b]) => {
    const el = document.getElementById('cap');
    el.innerHTML = `<div class="l1"><b>${a}</b></div>` + (b ? `<div class="l2">${b}</div>` : '');
    el.classList.add('on');
  }, [lines[0], lines[1] || '']);
  await beat(page, hold);
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

/** Opens a flow's canvas and waits for the graph to actually be there. */
async function canvas(page, flow) {
  await page.goto(`${STUDIO}/flow/${flow.id}`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.react-flow__node', { timeout: 60000 });
  await beat(page, 2200);
  const nodes = await page.locator('.react-flow__node').count();
  const edges = await page.locator('.react-flow__edge').count();
  console.log(`  canvas ${flow.name}: ${nodes} nodes, ${edges} edges`);
  await install(page);
  return { nodes, edges };
}

/** Runs one scenario in the Playground and returns what the agent answered. */
async function playground(page, ask, { timeout = 300000 } = {}) {
  // Drop the canvas caption first. The Playground is a modal over the same
  // page, so the overlay survives the click -- and a caption about the graph
  // then sits over the chat for as long as the answer takes.
  await page.evaluate(() => document.getElementById('cap')?.classList.remove('on'));
  await beat(page, 400);
  await page.click('button:has-text("Playground")');
  await page.waitForSelector('textarea, [contenteditable="true"]', { timeout: 60000 });
  await beat(page, 1600);
  await install(page);
  const box = page.locator('textarea, [contenteditable="true"]').last();
  await box.click();
  await box.fill(ask);
  await beat(page, 900);
  await page.keyboard.press('Enter');

  // Scope to the chat turns. The Playground is a modal over the canvas, so a
  // page-level selector reads the component palette instead of the answer --
  // which is how an earlier cut captioned four scenarios it had never read.
  const turns = page.locator('[data-testid*="chat-message"]');
  const started = Date.now();
  let seen = '';
  while (Date.now() - started < timeout) {
    const txt = ((await turns.last().innerText().catch(() => '')) || '').trim();
    if (txt && txt !== ask && txt === seen) break;   // stopped growing
    seen = txt;
    await beat(page, 1500);
  }
  if (!seen || seen === ask) {
    throw new Error('playground produced no answer');
  }
  if (/traceback|no matched type|internal server error/i.test(seen)) {
    throw new Error(`playground reported an error: ${seen.slice(0, 200)}`);
  }
  if (/[一-鿿]/.test(seen)) {
    throw new Error(`answer drifted out of Korean: ${seen.slice(0, 160)}`);
  }
  return seen;
}

async function scenario(page, key, copy) {
  const flow = FLOWS[key];
  if (!flow) throw new Error(`no flow built for ${key}`);
  await card(page, { head: copy.head }, 3600);
  await clearCard(page);
  await canvas(page, flow);
  if (copy.canvas) await say(page, copy.canvas, 6800);
  const answer = await playground(page, flow.ask);
  console.log(`  ran ${key}: ${answer.replace(/\s+/g, ' ').slice(-140)}`);
  await say(page, copy.run, 8000);
  await page.evaluate(() => document.getElementById('cap')?.classList.remove('on'));
  await beat(page, 500);
}

async function main() {
  mkdirSync('recording', { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    recordVideo: { dir: 'recording', size: { width: 1600, height: 1000 } },
  });
  const page = await ctx.newPage();

  await page.goto(`${BOX}/?lang=en`, { waitUntil: 'domcontentloaded' });
  await card(page, WEEK.title, 7500);

  // The premise, briefly: this is a box on a department LAN, and the drive is
  // where the documents live. The subject of the report is the agents, so this
  // gets one shot, not the film.
  await card(page, WEEK.premise, 6500);
  await page.fill('input[name=username]', 'admin');
  await page.fill('input[name=password]', 'meshbox');
  await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
                     page.click('button[type=submit]')]);
  await page.goto(`${BOX}/console/drives?lang=en`, { waitUntil: 'domcontentloaded' });
  await clearCard(page);
  await install(page);
  await say(page, WEEK.drive, 6000);
  await page.evaluate(() => document.getElementById('cap')?.classList.remove('on'));

  await login(page);
  for (const [key, copy] of [['legal', WEEK.legal], ['hr', WEEK.hr],
                             ['strategy', WEEK.strategy], ['support', WEEK.support]]) {
    await scenario(page, key, copy);
  }

  await card(page, WEEK.coverage, 9000);
  await card(page, WEEK.fixes, 9500);
  await card(page, WEEK.close, 7500);

  const video = page.video();
  await ctx.close();
  await video.saveAs(OUT);
  await browser.close();
  console.log(`wrote ${OUT}`);
}

main().catch((e) => { console.error(String(e.message || e)); process.exit(1); });
