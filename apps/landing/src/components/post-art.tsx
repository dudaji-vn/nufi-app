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

// For the "how it answers" post, step 1: documents are chunked and embedded on
// the box's GPU into a private index.
export function IndexingArt() {
  return (
    <div className="post-art">
      <svg viewBox="0 0 1400 400" role="img" aria-label="Documents are embedded on the box's GPU into a private index">
        {/* documents */}
        <rect className="pa-ink" x="150" y="94" width="140" height="182" rx="10" strokeWidth="5" opacity="0.3" />
        <rect className="pa-fill" x="170" y="112" width="140" height="182" rx="10" />
        <rect className="pa-ink" x="170" y="112" width="140" height="182" rx="10" strokeWidth="6" />
        <path
          className="pa-ink"
          d="M198 160 H282 M198 196 H282 M198 232 H264"
          strokeWidth="6"
          strokeLinecap="round"
          opacity="0.5"
        />
        <text className="pa-label" x="240" y="350" textAnchor="middle">your documents</text>
        {/* arrow */}
        <path className="pa-mute" d="M372 178 l24 25 l-24 25" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        {/* GPU */}
        <rect className="pa-fill" x="600" y="150" width="180" height="104" rx="10" />
        <rect className="pa-ink" x="600" y="150" width="180" height="104" rx="10" strokeWidth="6" />
        <rect className="pa-ink" x="660" y="182" width="60" height="40" rx="4" strokeWidth="4" />
        <path
          className="pa-ink"
          d="M636 150 v-16 M690 150 v-16 M744 150 v-16 M636 254 v16 M690 254 v16 M744 254 v16"
          strokeWidth="4"
          strokeLinecap="round"
        />
        <text className="pa-label" x="690" y="350" textAnchor="middle">embedded on the GPU</text>
        {/* arrow */}
        <path className="pa-mute" d="M844 178 l24 25 l-24 25" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        {/* index */}
        <rect className="pa-fill" x="1060" y="140" width="180" height="124" rx="10" />
        <rect className="pa-ink" x="1060" y="140" width="180" height="124" rx="10" strokeWidth="6" />
        <circle className="pa-dot" cx="1100" cy="172" r="9" />
        <circle className="pa-dot" cx="1150" cy="172" r="9" />
        <circle className="pa-dot" cx="1200" cy="172" r="9" />
        <circle className="pa-dot" cx="1100" cy="204" r="9" />
        <circle className="pa-dot" cx="1150" cy="204" r="9" />
        <circle className="pa-dot" cx="1200" cy="204" r="9" />
        <circle className="pa-dot" cx="1100" cy="236" r="9" />
        <circle className="pa-dot" cx="1150" cy="236" r="9" />
        <circle className="pa-dot" cx="1200" cy="236" r="9" />
        <text className="pa-label" x="1150" y="350" textAnchor="middle">a private index</text>
      </svg>
    </div>
  );
}

// Step 2: a question finds the matching pieces in the index; the model reads
// just those and writes an answer that cites its source.
export function AnsweringArt() {
  return (
    <div className="post-art">
      <svg viewBox="0 0 1400 400" role="img" aria-label="A question finds matching passages; the model answers with a citation">
        {/* question */}
        <rect className="pa-fill" x="132" y="128" width="168" height="110" rx="18" />
        <rect className="pa-ink" x="132" y="128" width="168" height="110" rx="18" strokeWidth="6" />
        <path className="pa-ink" d="M172 236 l0 34 l34 -34" strokeWidth="6" fill="none" strokeLinejoin="round" />
        <text className="pa-glyph" x="216" y="208" fontSize="70" textAnchor="middle">?</text>
        <text className="pa-label" x="216" y="350" textAnchor="middle">a question</text>
        {/* arrow */}
        <path className="pa-mute" d="M356 170 l24 25 l-24 25" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        {/* index with matches */}
        <rect className="pa-fill" x="560" y="130" width="180" height="124" rx="10" />
        <rect className="pa-ink" x="560" y="130" width="180" height="124" rx="10" strokeWidth="6" />
        <circle className="pa-dot" cx="600" cy="162" r="9" />
        <circle className="pa-dot" cx="650" cy="162" r="9" />
        <circle className="pa-dot" cx="700" cy="162" r="9" />
        <circle className="pa-dot" cx="600" cy="194" r="9" />
        <circle className="pa-dot--hot" cx="650" cy="194" r="11" />
        <circle className="pa-dot" cx="700" cy="194" r="9" />
        <circle className="pa-dot" cx="600" cy="226" r="9" />
        <circle className="pa-dot" cx="650" cy="226" r="9" />
        <circle className="pa-dot--hot" cx="700" cy="226" r="11" />
        <text className="pa-label" x="650" y="350" textAnchor="middle">the matching pieces</text>
        {/* arrow */}
        <path className="pa-mute" d="M808 170 l24 25 l-24 25" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        {/* answer with source */}
        <rect className="pa-fill" x="1000" y="120" width="210" height="150" rx="12" />
        <rect className="pa-ink" x="1000" y="120" width="210" height="150" rx="12" strokeWidth="6" />
        <path className="pa-ink" d="M1034 162 H1176 M1034 194 H1176" strokeWidth="5" strokeLinecap="round" opacity="0.5" />
        <path className="pa-accent" d="M1034 228 H1140" strokeWidth="7" strokeLinecap="round" />
        <text className="pa-label" x="1105" y="350" textAnchor="middle">an answer + its source</text>
      </svg>
    </div>
  );
}

// The box in five layers, top (what people use) to bottom (what it runs on). Names only; the post's
// tables carry versions and licenses.
const STACK: { layer: string; parts: string }[] = [
  { layer: 'chat + documents', parts: 'LibreChat · RAG API · pgvector · MongoDB' },
  { layer: 'models', parts: 'LiteLLM · Ollama · Qwen2.5 7B · BGE-M3' },
  { layer: 'agents + sandbox', parts: 'Langflow · Paperclip · gVisor · tinyproxy' },
  { layer: 'network + files', parts: 'Caddy · Tailscale · Headscale · Samba' },
  { layer: 'floor', parts: 'Docker · Ubuntu · Linux' },
];

export function BoxStackArt() {
  const top = 70;
  const h = 92;
  const gap = 18;
  return (
    <div className="post-art">
      <svg
        viewBox="0 0 1400 660"
        role="img"
        aria-label="NuFi Box in five layers of open-source projects, from chat and documents down to Docker and Linux"
      >
        <rect className="pa-ink" x="40" y="30" width="1320" height="600" rx="34" strokeWidth="4" opacity="0.5" />
        {STACK.map((s, i) => {
          const y = top + i * (h + gap);
          const last = i === STACK.length - 1;
          return (
            <g key={s.layer}>
              <rect className="pa-fill" x="80" y={y} width="1240" height={h} rx="18" />
              <rect
                className={last ? 'pa-mute' : 'pa-ink'}
                x="80"
                y={y}
                width="1240"
                height={h}
                rx="18"
                strokeWidth="4"
              />
              <text className="pa-label pa-label--accent" x="118" y={y + h / 2 + 10}>
                {s.layer}
              </text>
              <text className="pa-glyph" x="470" y={y + h / 2 + 11} fontSize="32">
                {s.parts}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
