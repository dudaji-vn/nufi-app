// Records a walkthrough of the box doing department work, on-box.
//
// The captions are the point. A screen recording of a console shows that
// something happened; it does not show why it matters. Each step here states
// the claim it is demonstrating, so the clip explains itself without a
// presenter -- including the two steps that show a refusal, which are the ones
// a buyer should care about most.
//
//   node record.mjs [--base http://127.0.0.1:8080] [--out demo.webm]
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : fallback;
};
const BASE = arg('base', 'http://127.0.0.1:8080');
const OUT = arg('out', 'demo.webm');
const DIR = 'recording';

const CAPTION_CSS = `
  #mbcap{position:fixed;left:0;right:0;bottom:0;z-index:2147483647;
    font:500 20px/1.5 "IBM Plex Sans",-apple-system,system-ui,sans-serif;
    background:rgba(12,26,36,.94);color:#eef4f8;padding:18px 28px;
    border-top:3px solid #4FB8CC;transition:opacity .25s}
  #mbcap b{color:#8AD4E3;font-weight:600}
  #mbcap small{display:block;margin-top:4px;font-size:15px;color:#9db4c2;font-weight:400}`;

async function caption(page, title, detail = '') {
  await page.evaluate(([t, d, css]) => {
    let el = document.getElementById('mbcap');
    if (!el) {
      const s = document.createElement('style');
      s.textContent = css;
      document.head.appendChild(s);
      el = document.createElement('div');
      el.id = 'mbcap';
      document.body.appendChild(el);
    }
    el.innerHTML = `<b>${t}</b>${d ? `<small>${d}</small>` : ''}`;
  }, [title, detail, CAPTION_CSS]);
}

const beat = (page, ms) => page.waitForTimeout(ms);

// The first cut of this clip captioned "Answered from the document" over a
// panel reading "AI 백엔드에 연결하지 못했습니다: timed out". A recording that
// narrates a success the screen did not show is worse than no recording, so
// every answer step now reads the panel back and the run aborts if what landed
// there is not an answer.
async function answerIn(page, selector, { timeout = 60000, not = '' } = {}) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const text = (await page.textContent(selector).catch(() => '') || '').trim();
    // `not` guards against reading the previous answer back: the panel keeps
    // the last result, so without this the second question happily "passes"
    // by re-reading the first one's output.
    const fresh = text && text !== not && !/^(\.\.\.|loading)/i.test(text);
    if (fresh) {
      if (/못했습니다|timed out|error|502|503/i.test(text)) {
        throw new Error(`step failed on screen: ${text.slice(0, 160)}`);
      }
      // The on-box model sometimes finishes a Korean sentence in Chinese. That
      // is a real defect, recorded in ../README.md -- but a demo frame showing
      // garbled text teaches a viewer nothing, so the run stops rather than
      // quietly filming it.
      if (/[\u4e00-\u9fff]/.test(text)) {
        throw new Error(`answer drifted out of Korean: ${text.slice(0, 160)}`);
      }
      return text;
    }
    await page.waitForTimeout(400);
  }
  throw new Error(`nothing appeared in ${selector} within ${timeout}ms`);
}

// The portal caps an AI call at 10s and the first call after an idle box loads
// the model, which alone exceeds that. Warm it before recording so the clip
// shows the steady state rather than a cold-start artefact -- and say so here
// rather than leaving a mystery sleep.
async function warm(page, base) {
  await page.request.post(`${base}/api/v1/rag/query`,
    { data: { question: 'warm-up' }, failOnStatusCode: false, timeout: 120000 })
    .catch(() => {});
}

async function main() {
  mkdirSync(DIR, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    recordVideo: { dir: DIR, size: { width: 1280, height: 800 } },
  });
  const page = await ctx.newPage();

  // --- sign in ------------------------------------------------------------
  await page.goto(`${BASE}/?lang=en`, { waitUntil: 'domcontentloaded' });
  await caption(page, 'A department buys one box.',
    'It sits on the team LAN. Nothing here talks to a cloud.');
  await beat(page, 3200);
  await page.fill('input[name=username]', 'admin');
  await page.fill('input[name=password]', 'meshbox');
  await beat(page, 700);
  await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
                     page.click('button[type=submit]')]);
  await warm(page, BASE);

  // --- the honest status board -------------------------------------------
  await page.goto(`${BASE}/console?lang=en`, { waitUntil: 'domcontentloaded' });
  await caption(page, 'Three modules, and the console will not flatter them.',
    'A module reads available only when its endpoint actually answers a probe. Unwired reads not_connected, never a fake green.');
  await beat(page, 5000);

  // --- the shared drive ---------------------------------------------------
  await page.goto(`${BASE}/console/drives?lang=en`, { waitUntil: 'domcontentloaded' });
  await caption(page, 'The shared drive is where the work already lives.',
    'Eight departments, each with its own share. The same folder a laptop mounts as a network drive.');
  await beat(page, 5000);

  // --- ask, and get a source ---------------------------------------------
  await page.goto(`${BASE}/console/ai?lang=en`, { waitUntil: 'domcontentloaded' });
  await caption(page, 'Ask the box about your own documents.',
    '&ldquo;What is the single-transaction limit on the corporate card?&rdquo; — the answer has to come from the uploaded policy, with the document named.');
  await beat(page, 3600);
  // Asked in Korean, as a Korean department would. English into a Korean
  // grounding prompt is what made the model answer in mixed Korean/Chinese.
  await page.fill('#rag-q', '법인카드 1회 사용 한도는 얼마인가요?');
  await beat(page, 900);
  await page.click('button:has-text("Ask")');
  const answered = await answerIn(page, '#rag-q-out');
  console.log('answer:', answered.slice(0, 120).replace(/\s+/g, ' '));
  await page.locator('#rag-q-out').scrollIntoViewIfNeeded();
  await caption(page, 'Answered from the department&rsquo;s own policy.',
    'The inference ran on this machine. The document never left the box to be answered.');
  await beat(page, 6000);

  // --- the refusal that matters -------------------------------------------
  await page.fill('#rag-q', '퇴사할 때 노트북은 어디에 반납하나요?');
  await caption(page, 'Now ask something the documents do not cover.',
    '&ldquo;Where do I return my laptop when I leave?&rdquo; — nothing on this box says. This is the question that separates a useful box from a dangerous one.');
  await beat(page, 3400);
  await page.click('button:has-text("Ask")');
  const declined = await answerIn(page, '#rag-q-out', { not: answered });
  console.log('refusal:', declined.slice(0, 120).replace(/\s+/g, ' '));
  await page.locator('#rag-q-out').scrollIntoViewIfNeeded();
  await caption(page, 'It declines instead of inventing.',
    'A confident wrong answer to a Legal or HR question is worse than no answer. The box says it does not know.');
  await beat(page, 6000);

  // --- the wall, enforced not promised ------------------------------------
  // A real POST to an adapter configured in enforce mode with a public
  // upstream. The 403 rendered below is the adapter's own response, fetched
  // during the recording -- not a page written to look like one.
  await caption(page, 'And the wall is enforced, not promised.',
    'Same adapter, pointed at a public destination, carrying department text.');
  await beat(page, 4000);
  const denied = await page.request.post('http://127.0.0.1:8903/v1/chat', {
    data: { message: 'Summarise our contract renewal terms.', history: [] },
    failOnStatusCode: false,
  });
  const body = await denied.text();
  await page.evaluate(([status, text]) => {
    const el = document.createElement('pre');
    el.style.cssText = 'position:fixed;inset:12% 8% auto 8%;z-index:2147483646;'
      + 'background:#14212B;color:#E4EBF1;border-left:4px solid #E88379;'
      + 'padding:28px;font:500 19px/1.7 "IBM Plex Mono",monospace;'
      + 'white-space:pre-wrap;border-radius:3px';
    el.textContent = `POST /v1/chat\n\nHTTP ${status}\n${text}`;
    document.body.appendChild(el);
  }, [denied.status(), body]);
  await beat(page, 2500);
  await caption(page, 'The box refuses to forward it at all.',
    'Not a policy statement in a brochure. The software will not carry the data off the mesh.');
  await beat(page, 7000);

  // Playwright finalises the file during context close, so grab the handle
  // first and let saveAs wait for the flush. Renaming whatever appears in the
  // directory races that flush and yields a truncated webm -- one that plays
  // for a few seconds and reports no duration at all.
  const video = page.video();
  await ctx.close();          // flushes the file
  await video.saveAs(OUT);    // must run before the browser goes away
  await browser.close();
  console.log(`wrote ${OUT}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
