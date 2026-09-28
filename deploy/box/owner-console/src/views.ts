import type { Health } from './health';
import type { BoxInfo } from './boxinfo';

// The result of a POST /invite, rendered back into the dashboard.
export type InviteResult = { link: string } | { error: string };

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

export function loginPage(error?: string): string {
  return shell('NuFi box · owner', `
  <h1>NuFi box owner</h1>
  <form method="post" action="/login">
    <label>Owner password<input type="password" name="password" autofocus required></label>
    <button type="submit">Sign in</button>
  </form>
  ${error ? `<p class="err">${esc(error)}</p>` : ''}`);
}

function serviceRows(health: Health[]): string {
  return health
    .map((h) => {
      const pill = h.ok
        ? `<span class="pill ok">up · ${h.ms}ms</span>`
        : `<span class="pill bad">${esc(h.error ? 'unreachable' : `HTTP ${h.status ?? '—'}`)}</span>`;
      return `<div class="row"><span class="name">${esc(h.name)}</span>${pill}</div>`;
    })
    .join('');
}

function meshPanel(info: BoxInfo): string {
  const m = info.mesh;
  if (!m.serverUrl) {
    return `<div class="row"><span class="name">Mesh</span><span class="pill">LAN-only</span></div>`;
  }
  if (!m.joined) {
    return `<div class="row"><span class="name">Mesh</span><span class="pill bad">not joined</span></div>
      <p class="sub">Coordinator ${esc(m.serverUrl)}${m.selfHost ? ' · self-hosted on this box' : ''} — run <code>nufi-box mesh up</code>.</p>`;
  }
  return `<div class="row"><span class="name">Mesh address</span><span class="pill ok">${esc(m.ip)}</span></div>
    <p class="sub">${esc(m.host)} · via ${esc(m.serverUrl)}${m.selfHost ? ' · self-hosted on this box' : ''}</p>`;
}

function invitePanel(info: BoxInfo, invite: InviteResult | undefined, canInvite: boolean): string {
  // Only offer the button when a mint can actually succeed (the console has both
  // a coordinator URL and an API key). Otherwise say precisely why not, rather
  // than a button that can only fail.
  let form: string;
  if (canInvite) {
    form = `<form method="post" action="/invite" style="flex-direction:row;margin-top:.5rem">
         <button type="submit">Generate an invite link</button>
       </form>`;
  } else if (info.mesh.serverUrl) {
    form = `<p class="sub">This console has no coordinator API key (<code>MESH_API_KEY</code>) to mint invites.</p>`;
  } else {
    form = `<p class="sub">Join a coordinator first (<code>nufi-box mesh up</code>) to invite members.</p>`;
  }
  let result = '';
  if (invite && 'link' in invite) {
    result = `<p class="sub" style="margin-top:.75rem">Share this link with the member — it works once and expires in an hour:</p>
      <input readonly value="${esc(invite.link)}" onclick="this.select()" style="width:100%;margin-top:.4rem">`;
  } else if (invite && 'error' in invite) {
    result = `<p class="err">${esc(invite.error)}</p>`;
  }
  return form + result;
}

// The owner dashboard: box identity, live service health, mesh status, the
// invite action, and the departments whose drives feed the assistants. `now`
// is passed in so the view is a pure function of its inputs (tested without a
// clock); `invite` renders the result of a just-submitted POST /invite.
export function dashboard(
  info: BoxInfo,
  health: Health[],
  now: Date,
  invite?: InviteResult,
  canInvite = false,
): string {
  const departments = info.departments.length
    ? info.departments.map((d) => `<code>${esc(d)}</code>`).join(' · ')
    : '<span class="sub">none configured</span>';
  const stamp = now.toISOString().slice(11, 19);
  return shell('NuFi box · owner', `
  <h1>${esc(info.name || 'NuFi box')}</h1>
  <p class="sub">${esc(info.host)}${info.ip ? ` · ${esc(info.ip)}` : ''}</p>

  <h2>Services</h2>
  <div class="grid">${serviceRows(health)}</div>

  <h2>Mesh</h2>
  <div class="grid">${meshPanel(info)}</div>

  <h2>Members</h2>
  ${invitePanel(info, invite, canInvite)}

  <h2>Departments</h2>
  <p>${departments}</p>

  <div class="foot">
    <span class="sub">checked ${stamp} UTC · <a href="/">refresh</a></span>
    <form method="post" action="/logout" style="margin:0"><button type="submit">Sign out</button></form>
  </div>`, true);
}
