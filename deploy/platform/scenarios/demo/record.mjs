// Records a walkthrough of the box doing department work, on-box.
//
// Two things this file refuses to do. It will not narrate a success the screen
// did not show -- every answer step reads the panel back and aborts on an error,
// a stale repeat, or an answer that drifted out of Korean. And the closing 403
// is a real POST made during the recording, rendered from the adapter's own
// reply, not a page written to look like one.
//
//   node record.mjs --lang en --out demo-en.webm
//   node record.mjs --lang ko --out demo-ko.webm
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { SCRIPT } from './script.mjs';
import { styles, diagram, THEME } from './stage.mjs';

const arg = (n, d) => {
  const i = process.argv.indexOf(`--${n}`);
  return i > -1 ? process.argv[i + 1] : d;
};
const BASE = arg('base', 'http://127.0.0.1:8080');
const LANG = arg('lang', 'en');
const DENY = arg('deny', 'http://127.0.0.1:8903');
const OUT = arg('out', `demo-${LANG}.webm`);
const T = SCRIPT[LANG];
if (!T) throw new Error(`no script for --lang ${LANG}`);

const beat = (p, ms) => p.waitForTimeout(ms);

async function install(page) {
  await page.evaluate(([css]) => {
    if (document.getElementById('mbstyle')) return;
    const s = document.createElement('style');
    s.id = 'mbstyle'; s.textContent = css; document.head.appendChild(s);
    const stage = document.createElement('div'); stage.id = 'stage';
    const cap = document.createElement('div'); cap.id = 'cap';
    document.body.append(stage, cap);
  }, [styles(T.font)]);
}

/** A full-screen card. `hold` includes the fade, so it is the real screen time. */
async function card(page, { eyebrow, head, sub = [], svg = '' }, hold = 6000) {
  await install(page);
  await page.evaluate(([e, h, s, g]) => {
    const el = document.getElementById('stage');
    el.innerHTML = (e ? `<div class="eyebrow">${e}</div>` : '')
      + `<h1>${h}</h1><div class="rule"></div>`
      + s.map((line) => `<p>${line}</p>`).join('') + g;
    el.classList.add('on');
    document.getElementById('cap').classList.remove('on');
  }, [eyebrow || '', head, sub, svg]);
  await beat(page, hold);
}

async function revealDiagram(page) {
  for (const g of ['g1', 'g2', 'g3']) {
    await page.evaluate((cls) => {
      const el = document.querySelector(`svg .${cls}`);
      if (el) { el.style.transition = 'opacity .7s ease'; el.style.opacity = '1'; }
    }, g);
    await beat(page, 1500);
  }
}

async function clearCard(page) {
  await page.evaluate(() => document.getElementById('stage')?.classList.remove('on'));
  await beat(page, 650);
}

/** Floating caption: an accented lead line, then the explanation. */
async function say(page, lines, hold = 5200) {
  await install(page);
  await page.evaluate(([l1, l2]) => {
    const el = document.getElementById('cap');
    el.innerHTML = `<div class="l1"><b>${l1}</b></div>`
      + (l2 ? `<div class="l2">${l2}</div>` : '');
    el.classList.add('on');
  }, [lines[0], lines[1] || '']);
  await beat(page, hold);
}

/** Reads the answer panel back; throws rather than let the caption lie. */
async function answerIn(page, sel, { timeout = 90000, not = '' } = {}) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const text = (await page.textContent(sel).catch(() => '') || '').trim();
    if (text && text !== not && !/^(\.\.\.|loading)/i.test(text)) {
      if (/못했습니다|timed out|error|502|503/i.test(text)) {
        throw new Error(`step failed on screen: ${text.slice(0, 160)}`);
      }
      if (/[一-鿿]/.test(text)) {
        throw new Error(`answer drifted out of Korean: ${text.slice(0, 160)}`);
      }
      return text;
    }
    await beat(page, 400);
  }
  throw new Error(`nothing appeared in ${sel} within ${timeout}ms`);
}

// The portal caps an AI call at 10s and a cold model load alone exceeds that,
// so the clip would otherwise open on a timeout that says nothing about the box.
async function warm(page) {
  await page.request.post(`${BASE}/api/v1/rag/query`,
    { data: { question: 'warm-up' }, failOnStatusCode: false, timeout: 180000 })
    .catch(() => {});
}

async function main() {
  mkdirSync('recording', { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 1,
    recordVideo: { dir: 'recording', size: { width: 1600, height: 1000 } },
  });
  const page = await ctx.newPage();

  await page.goto(`${BASE}/?lang=${LANG}`, { waitUntil: 'domcontentloaded' });

  // 1 — title
  await card(page, T.title, 7000);

  // 2 — how the two products meet.
  //
  // Everything slow happens here, behind a card that is meant to be read
  // anyway: signing in, warming the model (a cold load alone exceeds the
  // portal's 10s cap), and probing the three adapters. Doing it after the card
  // came down left the recording sitting on a motionless page for the better
  // part of a minute.
  await card(page, { ...T.arch, svg: diagram(THEME) }, 1400);
  const groundwork = (async () => {
    await page.fill('input[name=username]', 'admin');
    await page.fill('input[name=password]', 'meshbox');
    await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
                       page.click('button[type=submit]')]);
    const health = {};
    for (const [name, port] of [['chat', 8900], ['rag', 8901], ['agent', 8902]]) {
      const r = await page.request.get(`http://127.0.0.1:${port}/healthz`,
        { failOnStatusCode: false, timeout: 60000 }).catch(() => null);
      health[name] = r ? await r.text() : '(unreachable)';
    }
    await warm(page);
    return health;
  })();
  await revealDiagram(page);
  await beat(page, 5000);
  const health = await groundwork;

  // 3 — the seam answering for itself: three real /healthz replies
  await card(page, { head: T.seam.head, sub: [T.seam.body] }, 1200);
  await page.evaluate(([h, t]) => {
    const el = document.getElementById('stage');
    const pre = document.createElement('div');
    pre.style.cssText = `margin-top:26px;text-align:left;font:500 16px/2 "IBM Plex Mono",monospace;
      background:${t.panel};border:1px solid ${t.line};border-radius:12px;padding:24px 30px;
      color:${t.ink};max-width:1080px;overflow:hidden`;
    pre.innerHTML = Object.entries(h).map(([k, v]) =>
      `<div><span style="color:${t.accent2}">GET :${k === 'chat' ? 8900 : k === 'rag' ? 8901 : 8902}/healthz</span>  ${
        String(v).replace(/</g, '&lt;').slice(0, 150)}</div>`).join('');
    el.appendChild(pre);
  }, [health, THEME]);
  await say(page, T.seam.cap, 7000);
  await clearCard(page);

  // 4 — the console's honest status
  await page.goto(`${BASE}/console?lang=${LANG}`, { waitUntil: 'domcontentloaded' });
  await install(page);
  await say(page, T.status.cap, 6200);

  // 5 — the drive
  await page.goto(`${BASE}/console/drives?lang=${LANG}`, { waitUntil: 'domcontentloaded' });
  await install(page);
  await say(page, T.drive.cap, 6200);

  // 6 — a real question, verified before it is captioned
  await page.goto(`${BASE}/console/ai?lang=${LANG}`, { waitUntil: 'domcontentloaded' });
  await install(page);
  await say(page, T.ask.cap, 4200);
  await page.fill('#rag-q', '법인카드 1회 사용 한도는 얼마인가요?');
  await beat(page, 900);
  await page.click('button[onclick="askRag()"]');
  const answered = await answerIn(page, '#rag-q-out');
  console.log('answer  :', answered.slice(0, 110).replace(/\s+/g, ' '));
  await page.locator('#rag-q-out').scrollIntoViewIfNeeded();
  await say(page, T.ask.done, 7000);

  // 7 — the refusal
  await say(page, T.refuse.cap, 4200);
  await page.fill('#rag-q', '퇴사할 때 노트북은 어디에 반납하나요?');
  await beat(page, 900);
  await page.click('button[onclick="askRag()"]');
  const declined = await answerIn(page, '#rag-q-out', { not: answered });
  console.log('refusal :', declined.slice(0, 110).replace(/\s+/g, ' '));
  await page.locator('#rag-q-out').scrollIntoViewIfNeeded();
  await say(page, T.refuse.done, 7000);

  // 8 — the wall, made to refuse on camera
  await card(page, T.wall, 5000);
  const denied = await page.request.post(`${DENY}/v1/chat`, {
    data: { message: '계약 갱신 조건을 요약해줘.', history: [] },
    failOnStatusCode: false, timeout: 60000,
  });
  const body = await denied.text();
  if (denied.status() !== 403) {
    throw new Error(`egress step expected 403, got ${denied.status()}: ${body.slice(0, 120)}`);
  }
  await page.evaluate(([status, text, t]) => {
    const pre = document.createElement('pre');
    pre.style.cssText = `margin-top:30px;text-align:left;background:${t.panel};
      border:1px solid ${t.warn};border-left:4px solid ${t.warn};border-radius:12px;
      padding:26px 32px;font:500 19px/1.75 "IBM Plex Mono",monospace;color:${t.ink};
      white-space:pre-wrap;max-width:1060px`;
    pre.textContent = `POST /v1/chat\n\nHTTP ${status}\n${text}`;
    document.getElementById('stage').appendChild(pre);
  }, [denied.status(), body, THEME]);
  await beat(page, 2200);
  await say(page, T.wall.cap, 8000);

  // 9 — close
  await page.evaluate(() => document.getElementById('cap')?.classList.remove('on'));
  await card(page, T.close, 7500);

  const video = page.video();
  await ctx.close();
  await video.saveAs(OUT);
  await browser.close();
  console.log(`wrote ${OUT}`);
}

main().catch((e) => { console.error(String(e.message || e)); process.exit(1); });
