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
//
// Self-contained (no shell(), no external fonts/CDN): the box serves this on
// plain :80 to laptops that may be on an isolated LAN, so everything the page
// needs is inline. The look follows the owner-console design system (navy +
// Open Sans + cards); the "NF" mark mirrors web/src/app.tsx.
export function connectPage(): string {
  const runHints = {
    windows: 'On Windows, if SmartScreen says "Windows protected your PC", click More info, then Run anyway.',
    linux: 'On Linux, run it with:  bash <the downloaded file>',
  };
  const icons = {
    macos:
      '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16.37 1.43c.06 1.02-.33 2.02-1 2.75-.69.76-1.82 1.35-2.9 1.26-.1-1 .4-2.03 1.03-2.72.71-.78 1.94-1.35 2.87-1.29zM19.5 17.1c-.5 1.16-.74 1.67-1.38 2.69-.9 1.42-2.17 3.2-3.74 3.22-1.4.01-1.76-.9-3.66-.89-1.9.01-2.29.91-3.69.9-1.57-.02-2.77-1.63-3.67-3.05-2.52-4-2.78-8.7-1.23-11.2 1.1-1.78 2.84-2.81 4.47-2.81 1.67 0 2.71.91 4.09.91 1.34 0 2.15-.91 4.08-.91 1.46 0 3 .79 4.11 2.16-3.61 1.98-3.02 7.13.22 8.97z"/></svg>',
    windows:
      '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 5.1 10.6 4v7.6H3V5.1zm0 13.8L10.6 20v-7.5H3v6.4zM11.6 3.86 21 2.5v9.1h-9.4V3.86zm0 16.28L21 21.5v-9h-9.4v7.64z"/></svg>',
    linux:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 16h4"/></svg>',
  };
  const osButton = (os: 'macos' | 'windows' | 'linux', label: string) =>
    `<button type="button" class="os" data-os="${os}">${icons[os]}<span class="os-name">${label}</span></button>`;

  const script = `
  var tok = new URLSearchParams(location.hash.slice(1)).get('token');
  var msg = document.getElementById('msg');
  var picker = document.getElementById('picker');
  var steps = document.getElementById('steps');
  var hints = ${JSON.stringify(runHints)};
  function setMsg(text, kind) { msg.textContent = text; msg.className = 'note' + (kind ? ' ' + kind : ''); }
  if (!tok) {
    picker.hidden = true;
    setMsg('This link is missing its invite — ask the box owner for a new one.', 'err');
  } else {
    var ident = (navigator.platform || '') + ' ' + (navigator.userAgent || '');
    var guess = /Mac|iP(hone|ad|od)/i.test(ident) ? 'macos'
      : /Win/i.test(ident) ? 'windows'
      : /Linux|X11|CrOS/i.test(ident) ? 'linux' : '';
    if (guess) {
      var b = document.querySelector('[data-os="' + guess + '"]');
      if (b) { b.classList.add('detected'); b.insertAdjacentHTML('beforeend', '<span class="tag">Detected</span>'); }
    }
  }
  function renderMac(plan) {
    setMsg('You are all set once these three steps are done.', '');
    steps.hidden = false;
    steps.innerHTML =
      '<ol>' +
        '<li><div><div class="step-t">Install the NuFi Agent</div>' +
          '<div class="step-d">It is signed by Dudaji, so macOS opens it without a warning. Download it, then double-click to install.</div>' +
          '<a class="btn" id="pkg" download>Download for macOS</a></div></li>' +
        '<li><div><div class="step-t">Join the box</div>' +
          '<div class="step-d">Open <b>Terminal</b>, paste this line and press Return.</div>' +
          '<div class="cmd"><code id="cmd"></code><button type="button" id="copy">Copy</button></div></div></li>' +
        '<li><div><div class="step-t">Open NuFi</div>' +
          '<div class="step-d">Sign in and start chatting.</div>' +
          '<a class="btn" id="chat" target="_blank" rel="noopener"></a></div></li>' +
      '</ol>';
    document.getElementById('pkg').href = plan.pkgUrl;
    document.getElementById('cmd').textContent = plan.enroll;
    var chat = document.getElementById('chat'); chat.href = plan.chatUrl; chat.textContent = 'Open NuFi';
    var copy = document.getElementById('copy');
    copy.addEventListener('click', function () {
      var self = this;
      navigator.clipboard.writeText(plan.enroll).then(function () {
        self.textContent = 'Copied'; setTimeout(function () { self.textContent = 'Copy'; }, 1500);
      }).catch(function () {});
    });
  }
  function get(os) {
    setMsg('Preparing your connector…', ''); steps.hidden = true; steps.innerHTML = '';
    var member = (document.getElementById('member').value || '').trim();
    var bodyData = new URLSearchParams({ token: tok, os: os, member: member });
    fetch('/connect/connector', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: bodyData })
      .then(function (r) {
        if (!r.ok) { return r.text().then(function (t) { setMsg(t, 'err'); }); }
        if ((r.headers.get('content-type') || '').indexOf('application/json') !== -1) { return r.json().then(renderMac); }
        var cd = r.headers.get('content-disposition') || '';
        var m = cd.match(/filename="([^"]+)"/);
        var name = m ? m[1] : 'nufi-join.' + (os === 'windows' ? 'cmd' : 'sh');
        return r.blob().then(function (blob) {
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
          setMsg('Downloaded ' + name + '. ' + (hints[os] || ''), 'good');
        });
      })
      .catch(function () { setMsg('Could not reach the box. Are you on its network?', 'err'); });
  }
  var btns = document.querySelectorAll('[data-os]');
  for (var i = 0; i < btns.length; i++) {
    btns[i].addEventListener('click', function () { get(this.getAttribute('data-os')); });
  }
  `;

  return `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Join the NuFi box</title>
<style>
  :root{
    --navy:#293069;--navy-2:#3c4d8a;--ink:#333;--gray-1:#666;--gray-2:#999;
    --rule:#e6e6e6;--surface:#fff;--ground:#f6f7f9;--subtle:#f2f2f2;
    --ok:#1e8740;--bad:#c0392b;
    --radius-sm:6px;--radius:10px;--radius-lg:14px;
    --shadow-lg:0 12px 32px rgba(41,48,105,.18);
    --font:'Open Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
    --mono:Menlo,Monaco,Consolas,'Courier New',monospace;
    color-scheme:light dark;
  }
  @media (prefers-color-scheme:dark){
    :root{--ink:#e9ebf5;--gray-1:#aeb4cf;--gray-2:#8890b5;--rule:#333a5c;
      --surface:#1b2039;--ground:#12152a;--subtle:#242a47;--navy:#9fb0e6;--navy-2:#b8c4ef;}
  }
  *{box-sizing:border-box}
  body{margin:0;min-height:100dvh;display:flex;align-items:center;justify-content:center;
    background:var(--ground);color:var(--ink);font-family:var(--font);font-size:15px;line-height:1.55;
    padding:calc(16px + env(safe-area-inset-top,0px)) 16px calc(16px + env(safe-area-inset-bottom,0px));}
  .card{width:100%;max-width:27rem;background:var(--surface);border:1px solid var(--rule);
    border-radius:var(--radius-lg);box-shadow:var(--shadow-lg);padding:1.6rem 1.5rem;}
  .brand{display:flex;align-items:center;gap:.7rem;margin-bottom:1.3rem}
  .logo{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;flex:none;
    border-radius:var(--radius-sm);border:1.5px solid var(--navy);color:var(--navy);
    font-weight:700;font-size:16px;letter-spacing:.5px}
  h1{margin:0;font-size:1.3rem;font-weight:700;color:var(--navy)}
  .lede{margin:0 0 1.3rem;color:var(--gray-1);font-size:.92rem}
  .field{display:block;font-size:.85rem;color:var(--gray-1);margin:0 0 1.15rem}
  .field input{display:block;width:100%;margin-top:.35rem;padding:.6rem .7rem;font:inherit;color:var(--ink);
    background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius)}
  .field input:focus{outline:none;border-color:var(--navy-2);box-shadow:0 0 0 3px rgba(60,77,138,.18)}
  .pick-label{font-size:.85rem;color:var(--gray-1);margin:0 0 .55rem}
  .os-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem}
  .os{position:relative;display:flex;flex-direction:column;align-items:center;gap:.5rem;padding:.9rem .4rem;
    cursor:pointer;background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
    font:inherit;font-weight:600;color:var(--ink);transition:border-color .12s,background .12s,box-shadow .12s}
  .os:hover{border-color:var(--navy-2);background:var(--subtle)}
  .os:focus-visible{outline:none;box-shadow:0 0 0 3px rgba(60,77,138,.25)}
  .os svg{width:26px;height:26px;color:var(--navy)}
  .os-name{font-size:.85rem}
  .os.detected{border-color:var(--navy);box-shadow:inset 0 0 0 1px var(--navy)}
  .os .tag{position:absolute;top:-.55rem;right:-.3rem;font-size:.6rem;font-weight:700;letter-spacing:.04em;
    text-transform:uppercase;color:#fff;background:var(--navy);border-radius:999px;padding:.08rem .4rem}
  .note{margin:1.35rem 0 0;color:var(--gray-2);font-size:.8rem}
  .note.err{color:var(--bad)}
  .note.good{color:var(--ok)}
  #steps{margin-top:1.4rem}
  #steps ol{list-style:none;counter-reset:s;margin:0;padding:0;display:flex;flex-direction:column;gap:1.15rem}
  #steps li{counter-increment:s;display:grid;grid-template-columns:1.7rem 1fr;gap:.75rem;align-items:start}
  #steps li::before{content:counter(s);display:flex;align-items:center;justify-content:center;
    width:1.7rem;height:1.7rem;border-radius:999px;background:var(--navy);color:#fff;font-size:.82rem;font-weight:700}
  .step-t{font-weight:700;color:var(--ink)}
  .step-d{color:var(--gray-1);font-size:.88rem;margin:.15rem 0 .5rem}
  .btn{display:inline-block;cursor:pointer;text-decoration:none;font:inherit;font-weight:600;
    color:#fff;background:var(--navy);border:1px solid var(--navy);border-radius:var(--radius);padding:.5rem .9rem}
  .btn:hover{background:var(--navy-2);border-color:var(--navy-2)}
  .cmd{display:flex;gap:.4rem;align-items:flex-start}
  .cmd code{flex:1;display:block;white-space:pre-wrap;word-break:break-all;background:#0d1230;color:#d6e2ff;
    padding:.6rem .7rem;border-radius:var(--radius-sm);font-family:var(--mono);font-size:.78rem;line-height:1.5}
  .cmd button{flex:none;cursor:pointer;font:inherit;font-weight:600;color:#fff;background:var(--navy);
    border:1px solid var(--navy);border-radius:var(--radius-sm);padding:.4rem .7rem}
  .cmd button:hover{background:var(--navy-2);border-color:var(--navy-2)}
  @media (max-width:360px){.os-grid{grid-template-columns:1fr}}
</style>
</head><body>
  <main class="card">
    <div class="brand"><span class="logo" aria-hidden="true">NF</span><h1>Join the NuFi box</h1></div>
    <p class="lede">Connect this computer to your team's private AI. Pick your system and follow the steps — it installs the mesh client, trusts the box, and signs you in.</p>
    <div id="picker">
      <label class="field">Your name (optional)
        <input id="member" placeholder="e.g. Ivy" autocomplete="off">
      </label>
      <p class="pick-label">Choose your computer</p>
      <div class="os-grid">
        ${osButton('macos', 'macOS')}
        ${osButton('windows', 'Windows')}
        ${osButton('linux', 'Linux')}
      </div>
    </div>
    <div id="steps" hidden></div>
    <p id="msg" class="note">This link works once and expires — if it fails, ask for a fresh one.</p>
  </main>
  <script>${script}</script>
</body></html>`;
}

// The owner sign-in page. Self-contained + styled to the owner-console design
// system (navy + Open Sans + the "NF" mark), matching the Figma "Admin Access
// Key" frame: a centred card, the logo, a secret-key field with a show/hide eye.
export function loginPage(error?: string): string {
  return `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>NuFi box · Administrator Dashboard</title>
<style>
  :root{
    --navy:#293069;--navy-2:#3c4d8a;--ink:#333;--gray-1:#666;--gray-2:#999;
    --rule:#e6e6e6;--surface:#fff;--ground:#f6f7f9;--subtle:#f2f2f2;--bad:#c0392b;
    --radius:10px;--radius-lg:14px;--shadow-lg:0 12px 32px rgba(41,48,105,.14);
    --font:'Open Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
    color-scheme:light;
  }
  *{box-sizing:border-box}
  body{margin:0;min-height:100dvh;display:flex;align-items:center;justify-content:center;
    background:var(--ground);color:var(--ink);font-family:var(--font);font-size:15px;line-height:1.5;
    padding:calc(16px + env(safe-area-inset-top,0px)) 16px calc(16px + env(safe-area-inset-bottom,0px));}
  .card{width:100%;max-width:25rem;background:var(--surface);border:1px solid var(--rule);
    border-radius:var(--radius-lg);box-shadow:var(--shadow-lg);padding:2.25rem 2rem;text-align:center;}
  .logo{display:inline-flex;align-items:center;justify-content:center;margin:0 auto .4rem;}
  .logo svg{height:42px;width:auto;display:block;}
  h1{margin:1.1rem 0 .3rem;font-size:1.15rem;font-weight:700;letter-spacing:.06em;color:var(--ink);text-transform:uppercase;}
  .sub{margin:0 0 1.5rem;color:var(--gray-1);font-size:.9rem;}
  form{display:block;text-align:left;}
  .field{position:relative;display:block;}
  .field input{width:100%;padding:.7rem 2.6rem .7rem .8rem;font:inherit;color:var(--ink);background:var(--surface);
    border:1px solid var(--rule);border-radius:var(--radius);}
  .field input:focus{outline:none;border-color:var(--navy-2);box-shadow:0 0 0 3px rgba(60,77,138,.16);}
  .eye{position:absolute;top:50%;right:.5rem;transform:translateY(-50%);display:inline-flex;align-items:center;
    justify-content:center;width:2rem;height:2rem;border:0;background:transparent;color:var(--gray-2);cursor:pointer;border-radius:8px;}
  .eye:hover{color:var(--navy);}
  .btn{width:100%;margin-top:1rem;padding:.7rem;font:inherit;font-weight:600;color:#fff;background:var(--navy);
    border:1px solid var(--navy);border-radius:var(--radius);cursor:pointer;}
  .btn:hover{background:var(--navy-2);border-color:var(--navy-2);}
  .err{margin:1rem 0 0;color:var(--bad);font-size:.85rem;text-align:center;}
</style>
</head><body>
  <main class="card">
    <span class="logo" aria-hidden="true"><svg viewBox="0 0 427.28 183.69" role="img" aria-label="NuFi"><path fill="#3c4d8a" d="M217.81,128.96v53.15c-5.62-.03-11.04-.9-16.16-2.48-11.58-3.54-21.61-10.7-28.75-20.18l-.07-.07-23.53-22.75-5.27-5.09-18.28-17.67-10.53-10.18-5.79-5.6-6.8-6.57-.42-.41-15.8-15.27-7.74-7.49-8.39-8.11V.19c5.61.04,11.02.91,16.14,2.49,11.57,3.54,21.57,10.66,28.72,20.08l.02.03s.03.04.04.07c0,0,.01,0,.01.01h0s.01-.01.01-.01l22,22.76,6.8,7.03,15.19,15.72,13.62,14.08,3.6,3.73,4.79,4.95,2.13,2.21,18.28,18.91h0s1.57,1.63,1.57,1.63l14.59,15.08Z"/><path fill="#293069" d="M288.07,68.37v69.03c-1.8,8.11-5.36,15.58-10.26,21.99-4.95,6.47-11.28,11.88-18.55,15.8-8.24,4.44-17.71,6.96-27.77,6.96-.34,0-.69,0-1.03-.01v-113.05s.04.01.07.01c-.02-.1-.04-.21-.07-.31v-23.18h0c1.77-8.43,5.45-16.15,10.55-22.76,4.9-6.34,11.11-11.64,18.25-15.52,8.37-4.55,18.02-7.15,28.29-7.15.15,0,.32,0,.47.01v68.17h.04Z"/><path fill="#293069" d="M57.57,22.86V.19c-.15-.01-.3-.01-.45-.01-10.3,0-19.97,2.73-28.31,7.51h-.07c-6.73,3.84-12.58,9.01-17.24,15.16-5.01,6.61-8.59,14.35-10.34,22.76-.73,3.51-1.12,7.13-1.17,10.85v125.69h57.61V22.86h-.04Z"/><rect fill="#e99a97" x="335.09" y="96.66" width="57.7" height="56.68"/><rect fill="#3c4d8a" x="300.61" width="126.67" height="56.71"/></svg></span>
    <h1>Administrator Dashboard</h1>
    <p class="sub">Enter the admin secret key to access the dashboard.</p>
    <form method="post" action="/login">
      <label class="field">
        <input id="pw" type="password" name="password" placeholder="Enter secret key" autofocus required autocomplete="current-password">
        <button type="button" class="eye" id="toggle" aria-label="Show secret key">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
      </button>
      </label>
      <button type="submit" class="btn">Sign in</button>
    </form>
    ${error ? `<p class="err">${esc(error)}</p>` : ''}
  </main>
  <script>
  (function(){
    var pw=document.getElementById('pw'),t=document.getElementById('toggle');
    t.addEventListener('click',function(){
      var show=pw.type==='password';pw.type=show?'text':'password';
      t.setAttribute('aria-label',show?'Hide secret key':'Show secret key');
      pw.focus();
    });
  })();
  </script>
</body></html>`;
}
