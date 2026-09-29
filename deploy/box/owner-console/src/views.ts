import type { Health } from './health';
import type { BoxInfo } from './boxinfo';
import type { Node } from './mesh-api';

// The result of a POST /invite, rendered back into the dashboard.
export type InviteResult = { link: string } | { error: string };

// The mesh members to render: the node list, an error string if the coordinator
// could not be reached, or undefined when the box is not on a mesh at all.
export type MembersData = Node[] | { error: string } | undefined;

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
    macos: 'macOS: if it says the file is from an unidentified developer, right-click it and choose Open.',
    windows: 'Windows: if SmartScreen says "Windows protected your PC", click More info then Run anyway.',
    linux: 'Linux: run it with  bash <the downloaded file>.',
  };
  const script = `
  const tok = new URLSearchParams(location.hash.slice(1)).get('token');
  const msg = document.getElementById('msg');
  const picker = document.getElementById('picker');
  const hints = ${JSON.stringify(runHints)};
  if (!tok) { picker.hidden = true; msg.textContent = 'This link is missing its invite — ask the box owner for a new one.'; msg.className = 'err'; }
  async function get(os) {
    msg.className = 'sub'; msg.textContent = 'Preparing your connector…';
    const member = (document.getElementById('member').value || '').trim();
    const bodyData = new URLSearchParams({ token: tok, os, member });
    try {
      const r = await fetch('/connect/connector', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: bodyData });
      if (!r.ok) { msg.className = 'err'; msg.textContent = await r.text(); return; }
      const cd = r.headers.get('content-disposition') || '';
      const m = cd.match(/filename="([^"]+)"/);
      const name = m ? m[1] : 'nufi-join.' + (os === 'macos' ? 'command' : os === 'windows' ? 'cmd' : 'sh');
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove();
      msg.className = 'sub'; msg.textContent = 'Downloaded ' + name + '. ' + hints[os];
    } catch (e) { msg.className = 'err'; msg.textContent = 'Could not reach the box. Are you on its network?'; }
  }
  for (const b of document.querySelectorAll('[data-os]')) b.addEventListener('click', () => get(b.dataset.os));
  `;
  return shell('Join the NuFi box', `
  <h1>Join the NuFi box</h1>
  <p>Pick your computer and download the one-time connector, then run it. It installs the mesh client, trusts the box, and connects you.</p>
  <div id="picker">
    <label>Your name (optional)<input id="member" placeholder="e.g. Ivy" autocomplete="off"></label>
    <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:1rem">
      <button type="button" data-os="macos">macOS</button>
      <button type="button" data-os="windows">Windows</button>
      <button type="button" data-os="linux">Linux</button>
    </div>
  </div>
  <p id="msg" class="sub" style="margin-top:1.25rem">The connector works once and expires — if it fails, ask for a fresh link.</p>
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

// The current mesh members. The box's own node (tag:box, or its name) is shown
// without a Revoke button — you cannot cut the box off its own mesh from here.
function membersPanel(members: MembersData, boxName: string): string {
  if (members === undefined) return '';
  if ('error' in members) return `<p class="sub">Member list unavailable — ${esc(members.error)}</p>`;
  // The box's own node is identified by tag OR name (defence in depth against a
  // headscale tag-field change), computed once and used for both the filter and
  // the per-row action.
  const isBox = (n: Node) => n.tags.includes('tag:box') || n.name === boxName;
  if (members.filter((n) => !isBox(n)).length === 0) {
    return '<p class="sub" style="margin-top:.75rem">No members yet — generate an invite link above.</p>';
  }
  const rows = members
    .map((n) => {
      const pill = n.online ? '<span class="pill ok">online</span>' : '<span class="pill">offline</span>';
      const ip = n.ips[0] ? ` · ${esc(n.ips[0])}` : '';
      const seen = !n.online && n.lastSeen ? ` · last seen ${esc(n.lastSeen.slice(0, 10))}` : '';
      const action = isBox(n)
        ? '<span class="sub">this box</span>'
        : `<form method="post" action="/revoke" data-revoke data-name="${esc(n.name)}" style="margin:0;display:inline">
             <input type="hidden" name="id" value="${esc(n.id)}"><button type="submit">Revoke</button>
           </form>`;
      return `<div class="row"><span><span class="name">${esc(n.name || '(unnamed)')}</span><span class="sub">${ip}${seen}</span></span>
        <span style="display:flex;gap:.6rem;align-items:center">${pill}${action}</span></div>`;
    })
    .join('');
  return `<div class="grid" style="margin-top:.75rem">${rows}</div>`;
}

// How members reach each department's drive over SMB. Samba binds every address
// the box has, so the mesh name (when joined) and the LAN name both work; show
// the reachable one.
function drivesPanel(info: BoxInfo): string {
  if (info.departments.length === 0) return '<p class="sub">No departments configured.</p>';
  const host = info.mesh.joined && info.mesh.host ? info.mesh.host : info.host;
  const rows = info.departments
    .map((d) => `<div class="row"><span class="name">${esc(d)}</span>
      <code class="sub">\\\\${esc(host)}\\${esc(d)} · smb://${esc(host)}/${esc(d)}</code></div>`)
    .join('');
  return `<div class="grid">${rows}</div>`;
}

// The owner dashboard: box identity, live service health, mesh status, the
// invite action + current members, and the department drives. `now` is passed
// in so the view is a pure function of its inputs (tested without a clock);
// `invite` renders a just-submitted POST /invite; `members` the mesh node list.
export function dashboard(
  info: BoxInfo,
  health: Health[],
  now: Date,
  invite?: InviteResult,
  canInvite = false,
  members?: MembersData,
): string {
  const stamp = now.toISOString().slice(11, 19);
  const revokeScript = `
  for (const f of document.querySelectorAll('form[data-revoke]')) f.addEventListener('submit', (e) => {
    if (!confirm('Remove ' + f.dataset.name + '? They lose access to the box until invited again.')) e.preventDefault();
  });`;
  return shell('NuFi box · owner', `
  <h1>${esc(info.name || 'NuFi box')}</h1>
  <p class="sub">${esc(info.host)}${info.ip ? ` · ${esc(info.ip)}` : ''}</p>

  <h2>Services</h2>
  <div class="grid">${serviceRows(health)}</div>

  <h2>Mesh</h2>
  <div class="grid">${meshPanel(info)}</div>

  <h2>Members</h2>
  ${invitePanel(info, invite, canInvite)}
  ${membersPanel(members, info.name)}

  <h2>Department drives</h2>
  ${drivesPanel(info)}

  <div class="foot">
    <span class="sub">checked ${stamp} UTC · <a href="/">refresh</a></span>
    <form method="post" action="/logout" style="margin:0"><button type="submit">Sign out</button></form>
  </div>
  <script>${revokeScript}</script>`, true);
}
