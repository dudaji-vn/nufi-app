// The look: full-screen cards between live shots, and a floating caption card
// over them. Kept separate from the storyboard so changing the design never
// risks changing what the recording claims.
export const THEME = {
  bg: '#0B0A14', ink: '#F2F1F8', dim: '#9C99B4',
  accent: '#7C6BF5', accent2: '#A99BFF', warn: '#F08A7E', ok: '#5FCF98',
  panel: '#151327', line: '#282542',
};

export function styles(font) {
  const t = THEME;
  return `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
  #stage,#cap{font-family:${font}}
  /* pointer-events:none throughout -- the presentation layer must never
     intercept a click meant for the app underneath, or the recording starts
     filming the overlay instead of the product. */
  #stage{position:fixed;inset:0;z-index:2147483600;background:${t.bg};color:${t.ink};
    display:flex;flex-direction:column;align-items:center;justify-content:center;
    text-align:center;padding:0 8vw;opacity:0;pointer-events:none;
    transition:opacity .55s ease}
  #stage.on{opacity:1}
  #stage .eyebrow{font:600 14px/1 "IBM Plex Mono",monospace;letter-spacing:.22em;
    color:${t.accent2};text-transform:uppercase;margin-bottom:34px}
  /* keep-all is the correct break rule for Korean: without it the browser
     breaks mid-word and a headline reads "집행입니 / 다." */
  #stage h1{font-size:52px;font-weight:700;line-height:1.2;margin:0;max-width:22ch;
    letter-spacing:-.02em;word-break:keep-all;text-wrap:balance}
  #stage .rule{width:64px;height:3px;background:${t.accent};margin:34px 0;border-radius:2px}
  #stage p{margin:0 0 10px;font-size:21px;line-height:1.65;color:${t.dim};max-width:62ch;
    word-break:keep-all}
  #stage .diagram{margin-top:8px}

  #cap{position:fixed;left:50%;transform:translateX(-50%);bottom:44px;z-index:2147483647;
    background:rgba(17,15,32,.965);border:1px solid ${t.line};border-radius:14px;
    padding:22px 34px;max-width:78vw;box-shadow:0 22px 60px rgba(0,0,0,.55);
    text-align:center;opacity:0;pointer-events:none;transition:opacity .3s ease}
  #cap.on{opacity:1}
  #cap b{color:${t.accent2};font-weight:600}
  #cap .l1{font-size:23px;line-height:1.45;color:${t.ink};font-weight:500;word-break:keep-all}
  #cap .l2{font-size:18px;line-height:1.6;color:${t.dim};margin-top:8px;word-break:keep-all}
  `;
}

// One SVG, drawn once, revealed in three beats so the eye follows the path a
// question actually takes rather than meeting the whole graph at once.
export function diagram(t = THEME) {
  const box = (x, y, w, h, fill, stroke) =>
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`;
  const label = (x, y, s, size, fill, weight = 500) =>
    `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" font-weight="${weight}" text-anchor="middle">${s}</text>`;
  return `
<svg class="diagram" width="1180" height="330" viewBox="0 0 1180 330" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="ar" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">
      <path d="M0,0 L9,4.5 L0,9 z" fill="${t.accent}"/>
    </marker>
  </defs>

  <g class="g1" opacity="0">
    ${box(20, 118, 168, 88, t.panel, t.line)}
    ${label(104, 150, '\u{1F4BB}', 22, t.ink)}
    ${label(104, 178, 'Member laptop', 15, t.dim)}
    <path d="M192 162 H 268" stroke="${t.accent}" stroke-width="2" marker-end="url(#ar)"/>
    ${label(230, 148, 'mesh', 12, t.accent2)}
  </g>

  <g class="g2" opacity="0">
    ${box(276, 60, 300, 210, '#171433', t.accent)}
    ${label(426, 92, 'MeshBox', 19, t.ink, 700)}
    ${label(426, 116, 'the box', 13, t.accent2)}
    ${label(426, 152, 'portal · console', 14, t.dim)}
    ${label(426, 176, 'shared drives · audit', 14, t.dim)}
    ${label(426, 200, 'mesh VPN', 14, t.dim)}
    ${label(426, 240, 'runs no model', 13, t.warn)}
    <path d="M580 162 H 656" stroke="${t.accent}" stroke-width="2" marker-end="url(#ar)"/>
    ${label(618, 148, '/v1/*', 12, t.accent2)}
  </g>

  <g class="g3" opacity="0">
    ${box(664, 60, 232, 210, t.panel, t.line)}
    ${label(780, 92, '3 adapters', 18, t.ink, 700)}
    ${label(780, 116, 'nufi-app', 13, t.accent2)}
    ${label(780, 152, 'chat · 8900', 14, t.dim)}
    ${label(780, 176, 'rag · 8901', 14, t.dim)}
    ${label(780, 200, 'agent · 8902', 14, t.dim)}
    ${label(780, 240, 'the whole integration', 13, t.ok)}
    <path d="M900 162 H 976" stroke="${t.accent}" stroke-width="2" marker-end="url(#ar)"/>
    ${box(984, 118, 176, 88, '#171433', t.accent)}
    ${label(1072, 152, 'On-box model', 15, t.ink, 600)}
    ${label(1072, 178, 'never leaves', 13, t.ok)}
  </g>
</svg>`;
}
