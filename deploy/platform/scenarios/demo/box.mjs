// The narration for the NuFi box introduction film. English, in the format
// the weekly recordings set: dark full-screen cards, a floating caption over
// live footage, a mono eyebrow, a short rule. Written as a normal product
// introduction — what the box is, how it goes on, how a department uses it,
// and how someone reaches it from home.
//
// Every figure named here is one the filmed box actually produces: the four
// URLs come off the real installer banner, the citation is the file the
// legal drive holds, and the mesh lines are this box's own `mesh status`.
export const BOX = {
  title: {
    eyebrow: 'THE NUFI TEAM BOX',
    head: 'Your team’s knowledge, on a machine you own',
    sub: ['One command puts the whole of NuFi on a machine in the office &mdash; chat, agents and the model itself.',
          'A shared folder becomes the team&rsquo;s knowledge. Nothing leaves the box.'],
  },

  install: {
    eyebrow: 'ONE COMMAND',
    head: 'From a blank machine to four URLs',
    sub: ['On a fresh Ubuntu or Mac, one script installs everything and prints where to go.',
          'No cloud account, no keys to paste, no per-seat licence.'],
  },
  installCap: ['<b>One command, four questions, a banner.</b>',
               'The box names its own address, its login, and the folder each team drops files into.'],

  premise: {
    eyebrow: 'THE IDEA',
    head: 'A folder is the interface',
    sub: ['Each department gets one folder. Drop a file in, and a minute later the team&rsquo;s agent can answer from it.',
          'No upload screen, no per-file permission, no button to press.'],
  },

  drop: ['<b>A document goes into the Legal folder.</b>',
         'About a minute later it is knowledge the Legal agent can answer from &mdash; and cite.'],
  ask: ['<b>Ask in plain language.</b>',
        'The model runs on the box itself. The question, the documents and the answer never leave the machine.'],
  cite: ['<b>The answer names the file it came from.</b>',
         'Governed by Vietnamese law, VIAC in Hanoi &mdash; read straight out of the NDA in the folder, not the model&rsquo;s memory.'],

  studio: {
    eyebrow: 'ON THE SAME BOX',
    head: 'Routines a team runs without opening a canvas',
    sub: ['Studio &mdash; the flow canvas &mdash; ships on every box, with the department routines already in it.',
          'A member presses Run; the flow reaches the same on-box model.'],
  },
  studioCap: ['<b>The routines ship ready to run.</b>',
              'Each is a flow small enough to read and open enough to change. Nothing is locked.'],

  mesh: {
    eyebrow: 'FROM HOME',
    head: 'The same box, reached from anywhere',
    sub: ['A laptop on a hotspot joins the box&rsquo;s private network with one file.',
          'The box stays in the office and keeps the documents; only the person is remote.'],
  },
  meshStatus: ['<b>The box has a name that resolves from anywhere.</b>',
               'It joins a small coordinator that holds no documents and no model &mdash; only the list of machines allowed on.'],
  meshInvite: ['<b>One file invites a laptop.</b>',
               'Run it, and the box answers at its own name over an encrypted link &mdash; same login, same drives, same certificate.'],

  close: {
    eyebrow: 'THE NUFI TEAM BOX',
    head: 'One machine. The whole product. Nothing leaves it.',
    sub: ['Installed in one command, used through a folder, reached from anywhere its team is.',
          'Chat, agents, Studio and the model &mdash; on hardware the department already owns.'],
  },

  // ---- detailed cut only -------------------------------------------------
  whatYouGet: {
    eyebrow: 'WHAT YOU GET',
    head: 'The whole of NuFi, on one machine',
    sub: ['<b>Chat</b> for every team &middot; <b>Console</b>, the box&rsquo;s identity and model gateway.',
          '<b>Admin panel</b> for accounts and audit &middot; <b>Studio</b>, the flow canvas.',
          'One login works across all four. A member signs in once and never sees a second password.'],
  },
  driveFill: {
    eyebrow: 'THE IDEA, IN ONE STEP',
    head: 'A file goes in; a minute later it is knowledge',
    sub: ['No upload screen and no button &mdash; the department&rsquo;s folder is an ordinary network share.',
          'The box watches it, waits for the file to finish copying, and embeds it.'],
  },
  driveFillCap: ['<b>Drop a document in the folder.</b>',
                 'The box picks it up on its own and reports it embedded &mdash; ready to answer from.'],

  term: ['<b>Ask again, and it stays on the document.</b>',
         'Three years, straight from the NDA&rsquo;s term clause &mdash; not a number the model made up.'],
  absent: ['<b>And it says when the answer is not there.</b>',
           'Asked something the Legal folder does not hold, it declines rather than guessing.'],

  separation: {
    eyebrow: 'PER DEPARTMENT',
    head: 'Each agent reads only its own folder',
    sub: ['The Legal agent reads the Legal drive; the HR agent reads HR&rsquo;s.',
          'Asking one about the other&rsquo;s documents gets an honest &ldquo;not in these documents&rdquo;, never a wrong answer from the wrong folder.'],
  },
  hr: ['<b>The HR agent answers from the HR folder.</b>',
       '15 days, 18 from the fourth year &mdash; read out of the leave policy, the same way the Legal agent reads the NDA.'],

  dayTwo: {
    eyebrow: 'DAY TWO',
    head: 'The box looks after itself',
    sub: ['One command shows every service, the model and the disk. Another checks the things that break and says what to do.',
          '<code>update</code> fetches the box, checks it, and rolls back on its own if the check fails.'],
  },
  dayTwoCap: ['<b>Thirteen services, one line to see them all.</b>',
              'status, doctor, backup, update, support &mdash; day two without knowing Docker.'],

  notYet: {
    eyebrow: 'WHAT IT IS NOT, YET',
    head: 'Being straight about the edges',
    sub: ['It does not read or send email, and it does not record meetings &mdash; it summarises a transcript you give it.',
          'Updates are checked and roll back on their own, but are not signed yet. On the LAN and over the mesh, it is solid.'],
  },
};

// The real command output the film shows as styled terminals. Captured from
// the filmed box on 22 September 2026; not retyped by hand.
export const TERMINAL = {
  install: [
    ['prompt', './install-box.sh --yes'],
    ['dim', '  Four questions  →  box name · admin email · departments · model'],
    ['dim', '  Pulling images, starting 13 services, creating the admin…'],
    ['blank', ''],
    ['ok', '  NuFi box "nufi" is up.'],
    ['blank', ''],
    ['out', '  Chat:        https://nufi.local:3080'],
    ['out', '  Agents:      https://nufi.local:3001/choose'],
    ['out', '  Console:     https://nufi.local:3001'],
    ['out', '  Admin panel: https://nufi.local:3002'],
    ['accent', '  Certificate: http://nufi.local/   ← laptops trust it once'],
    ['blank', ''],
    ['out', '  Drives:      data/drives/<department>  → the team’s knowledge'],
  ],
  drop: [
    ['prompt', 'cp NDA-Standard-Clauses.md  data/drives/legal/'],
    ['dim', '  # nothing else to do — the box is watching the folder'],
    ['blank', ''],
    ['prompt', 'nufi-box logs nufi-ingest'],
    ['ok', '  added legal/NDA-Standard-Clauses.md → d3df91d0… (embedded=True)'],
    ['dim', '  # about a minute after the copy'],
  ],
  flows: [
    ['prompt', 'nufi-box flows list'],
    ['out', '  Routine · ask the department drive'],
    ['out', '  Routine · meeting transcript to decisions'],
    ['out', '  Routine · weekly report from the drive'],
    ['out', '  Sales · RFP to requirement checklist'],
    ['dim', '  …'],
    ['blank', ''],
    ['ok', '  14 flow(s) — open, edit, or run any of them'],
  ],
  status: [
    ['prompt', 'nufi-box status'],
    ['out', '  admin-panel   console   litellm-proxy   mongodb   postgres'],
    ['out', '  librechat     caddy     nufi-ingest     nufi-cron  ollama'],
    ['out', '  rag_api       samba     studio          tailscale'],
    ['ok', '  13 services up (healthy)'],
    ['blank', ''],
    ['dim', '  Model: qwen2.5-3b via ollama-docker'],
    ['dim', '  Disk: 31G used of 38G   Last backup: 20260918'],
  ],
  update: [
    ['prompt', 'nufi-box update'],
    ['dim', '  Fetching main, snapshotting the current box…'],
    ['dim', '  Re-installing, then checking with doctor…'],
    ['blank', ''],
    ['ok', '  Updated to main (4f62b47)'],
    ['dim', '  # if doctor had failed, it would have rolled itself back'],
  ],
  mesh: [
    ['prompt', 'nufi-box mesh status'],
    ['out', '  coordinator    https://mesh.nufi.me'],
    ['out', '  mesh address   100.64.0.1'],
    ['accent', '  MagicDNS name  nufi.box.nufi.me'],
    ['blank', ''],
    ['dim', '  # every product now answers on that name, from anywhere'],
  ],
  invite: [
    ['prompt', 'nufi-box invite alice --os macos --drives legal,hr'],
    ['ok', '  Wrote data/invites/nufi-join-alice.command'],
    ['dim', '  Send it to alice: "Run this file, then open'],
    ['accent', '  https://nufi.box.nufi.me:3080 — the key inside works once."'],
  ],
};
