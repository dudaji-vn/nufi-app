const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const shell = (title: string, body: string, wide = false) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<style>
  :root{color-scheme:light dark}
  body{font:16px/1.5 system-ui,sans-serif;max-width:${wide ? '44rem' : '24rem'};margin:${wide ? '2.5rem' : '4rem'} auto;padding:0 1rem}
  h1{font-weight:600;font-size:1.4rem}
  h2{font-size:1rem;text-transform:uppercase;letter-spacing:.05em;opacity:.6;margin:1.75rem 0 .5rem}
  form{display:flex;flex-direction:column;gap:.75rem;margin-top:1.5rem}
  input,button{font:inherit;padding:.6rem .7rem;border-radius:8px;border:1px solid #8886}
  button{cursor:pointer;font-weight:600}
  .err{color:#c0392b;margin-top:1rem}
  .sub{opacity:.6;font-size:.9rem}
  .grid{display:grid;grid-template-columns:1fr;gap:.5rem}
  .row{display:flex;align-items:center;justify-content:space-between;gap:.75rem;
       padding:.6rem .8rem;border:1px solid #8883;border-radius:10px}
  .pill{font-size:.8rem;font-weight:600;padding:.15rem .55rem;border-radius:999px;white-space:nowrap}
  .ok{background:#1e874022;color:#1e8740}
  .bad{background:#c0392b22;color:#c0392b}
  .name{font-weight:600}
  .foot{display:flex;align-items:center;justify-content:space-between;margin-top:2rem}
  a{color:inherit}
  code{font-size:.9em}
</style></head><body>${body}</body></html>`;

// The member-facing join page. No login — the invite token is the credential,
// and it arrives in the URL #fragment (read here client-side, never sent to the
// server on the GET). The member picks their OS and downloads the connector;
// the token is POSTed to /connect/connector only when they do.
export function connectPage(): string {
  const runHints = {
    windows: 'Windows: if SmartScreen says "Windows protected your PC", click More info then Run anyway.',
    linux: 'Linux: run it with  bash <the downloaded file>.',
  };
  const script = `
  const tok = new URLSearchParams(location.hash.slice(1)).get('token');
  const msg = document.getElementById('msg');
  const picker = document.getElementById('picker');
  const steps = document.getElementById('steps');
  const hints = ${JSON.stringify(runHints)};
  if (!tok) { picker.hidden = true; msg.textContent = 'This link is missing its invite — ask the box owner for a new one.'; msg.className = 'err'; }
  function renderMac(plan) {
    msg.className = 'sub'; msg.textContent = 'Three steps to join:';
    steps.hidden = false;
    steps.innerHTML =
      '<ol>' +
      '<li>Download and install the app, then double-click it (it is signed — no warning): ' +
        '<a id="pkg" download>NuFi Agent for macOS</a></li>' +
      '<li>Open <b>Terminal</b>, paste this and press Return: ' +
        '<div class="cmd"><code id="cmd"></code><button type="button" id="copy">Copy</button></div></li>' +
      '<li>Open NuFi and sign in: <a id="chat"></a></li>' +
      '</ol>';
    document.getElementById('pkg').href = plan.pkgUrl;
    document.getElementById('cmd').textContent = plan.enroll;
    const chat = document.getElementById('chat'); chat.href = plan.chatUrl; chat.textContent = plan.chatUrl;
    document.getElementById('copy').addEventListener('click', async function () {
      try { await navigator.clipboard.writeText(plan.enroll); this.textContent = 'Copied'; setTimeout(() => { this.textContent = 'Copy'; }, 1500); } catch (e) {}
    });
  }
  async function get(os) {
    msg.className = 'sub'; msg.textContent = 'Preparing…'; steps.hidden = true; steps.innerHTML = '';
    const member = (document.getElementById('member').value || '').trim();
    const bodyData = new URLSearchParams({ token: tok, os, member });
    try {
      const r = await fetch('/connect/connector', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: bodyData });
      if (!r.ok) { msg.className = 'err'; msg.textContent = await r.text(); return; }
      if ((r.headers.get('content-type') || '').includes('application/json')) { renderMac(await r.json()); return; }
      const cd = r.headers.get('content-disposition') || '';
      const m = cd.match(/filename="([^"]+)"/);
      const name = m ? m[1] : 'nufi-join.' + (os === 'windows' ? 'cmd' : 'sh');
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
      msg.className = 'sub'; msg.textContent = 'Downloaded ' + name + '. ' + (hints[os] || '');
    } catch (e) { msg.className = 'err'; msg.textContent = 'Could not reach the box. Are you on its network?'; }
  }
  for (const b of document.querySelectorAll('[data-os]')) b.addEventListener('click', () => get(b.dataset.os));
  `;
  return shell('Join the NuFi box', `
  <h1>Join the NuFi box</h1>
  <p>Pick your computer and follow the steps. It installs the mesh client, trusts the box, and connects you.</p>
  <div id="picker">
    <label>Your name (optional)<input id="member" placeholder="e.g. Ivy" autocomplete="off"></label>
    <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:1rem">
      <button type="button" data-os="macos">macOS</button>
      <button type="button" data-os="windows">Windows</button>
      <button type="button" data-os="linux">Linux</button>
    </div>
  </div>
  <div id="steps" hidden style="margin-top:1.25rem"></div>
  <p id="msg" class="sub" style="margin-top:1.25rem">The link works once and expires — if it fails, ask for a fresh one.</p>
  <style>
    #steps ol { padding-left: 1.2rem; line-height: 1.7; }
    #steps .cmd { display:flex; gap:.5rem; align-items:flex-start; margin-top:.4rem; }
    #steps code { display:block; flex:1; white-space:pre-wrap; word-break:break-all; background:#0b1020; color:#d6e2ff; padding:.6rem .7rem; border-radius:.4rem; font-size:.82rem; }
    #steps button { flex:0 0 auto; }
  </style>
  <script>${script}</script>`);
}

export function loginPage(error?: string): string {
  return shell('NuFi box · owner', `
  <h1>NuFi box owner</h1>
  <form method="post" action="/login">
    <label>Owner password<input type="password" name="password" autofocus required></label>
    <button type="submit">Sign in</button>
  </form>
  ${error ? `<p class="err">${esc(error)}</p>` : ''}`);
}
