// A small conceptual diagram for the "nothing leaves the box" post: a sealed box
// (your docs + GPU) with a route out that's blocked, and the internet unreachable.
// Themed via tokens so it works in light and dark, and inside a card or the article.
export function SealedBoxArt() {
  return (
    <div className="post-art">
      <svg viewBox="0 0 1400 560" role="img" aria-label="A sealed box with no route to the internet">
        {/* sealed perimeter */}
        <rect
          className="pa-ink"
          x="150"
          y="120"
          width="490"
          height="320"
          rx="34"
          strokeWidth="4"
          strokeDasharray="2 16"
          strokeLinecap="round"
          opacity="0.5"
        />
        {/* the box */}
        <rect className="pa-fill" x="182" y="152" width="426" height="256" rx="24" />
        <rect className="pa-ink" x="182" y="152" width="426" height="256" rx="24" strokeWidth="6" />
        {/* lock inside the box */}
        <rect className="pa-ink" x="352" y="284" width="86" height="62" rx="10" strokeWidth="6" />
        <path className="pa-ink" d="M368 284 v-18 a27 27 0 0 1 54 0 v18" strokeWidth="6" />
        {/* route out, cut */}
        <path className="pa-ink" d="M636 280 H742" strokeWidth="6" strokeLinecap="round" />
        <path className="pa-mute" d="M812 280 H904" strokeWidth="6" strokeLinecap="round" strokeDasharray="2 18" />
        <circle className="pa-card" cx="777" cy="280" r="40" />
        <circle className="pa-accent" cx="777" cy="280" r="40" strokeWidth="6" />
        <path className="pa-accent" d="M761 264 l32 32 M793 264 l-32 32" strokeWidth="6" strokeLinecap="round" />
        {/* the internet, unreachable */}
        <circle className="pa-mute" cx="1120" cy="280" r="82" strokeWidth="5" />
        <ellipse className="pa-mute" cx="1120" cy="280" rx="34" ry="82" strokeWidth="5" />
        <path className="pa-mute" d="M1038 280 H1202 M1056 232 H1184 M1056 328 H1184" strokeWidth="5" />
        {/* labels */}
        <text className="pa-label" x="395" y="494" textAnchor="middle">your box</text>
        <text className="pa-label" x="1120" y="420" textAnchor="middle">the internet</text>
        <text className="pa-label pa-label--accent" x="777" y="206" textAnchor="middle">no route</text>
      </svg>
    </div>
  );
}

// For the air-gap post: a box with its network cable unplugged, the internet
// slack and unreachable. Same tokens/classes as SealedBoxArt.
export function UnpluggedBoxArt() {
  return (
    <div className="post-art">
      <svg viewBox="0 0 1400 560" role="img" aria-label="A box with its internet cable unplugged">
        {/* the box */}
        <rect className="pa-fill" x="168" y="150" width="384" height="260" rx="24" />
        <rect className="pa-ink" x="168" y="150" width="384" height="260" rx="24" strokeWidth="6" />
        {/* documents inside */}
        <path
          className="pa-ink"
          d="M232 236 H480 M232 276 H480 M232 316 H412"
          strokeWidth="6"
          strokeLinecap="round"
          opacity="0.4"
        />
        {/* network socket on the box edge */}
        <rect className="pa-ink" x="540" y="258" width="34" height="44" rx="4" strokeWidth="5" />
        {/* unplugged RJ45 plug + pins facing the socket */}
        <rect className="pa-ink" x="648" y="256" width="66" height="48" rx="5" strokeWidth="5" />
        <path className="pa-ink" d="M668 256 v-10 h26 v10" strokeWidth="4" />
        <path className="pa-ink" d="M648 270 h-14 M648 282 h-14 M648 294 h-14" strokeWidth="4" strokeLinecap="round" />
        {/* the break */}
        <path className="pa-accent" d="M604 258 l-12 22 l18 0 l-12 24" strokeWidth="5" strokeLinejoin="round" />
        {/* slack cable to the internet */}
        <path className="pa-mute" d="M714 284 C 840 372, 980 360, 1086 290" strokeWidth="5" />
        {/* the internet, unreachable */}
        <circle className="pa-mute" cx="1154" cy="280" r="72" strokeWidth="5" />
        <ellipse className="pa-mute" cx="1154" cy="280" rx="30" ry="72" strokeWidth="5" />
        <path className="pa-mute" d="M1082 280 H1226 M1098 236 H1210 M1098 324 H1210" strokeWidth="5" />
        {/* labels */}
        <text className="pa-label" x="360" y="466" textAnchor="middle">your box</text>
        <text className="pa-label" x="1154" y="392" textAnchor="middle">the internet</text>
        <text className="pa-label pa-label--accent" x="604" y="232" textAnchor="middle">unplugged</text>
      </svg>
    </div>
  );
}
