const F = (v: string) => ({ fill: `rgb(var(--${v}))` });
const S = (v: string, w = 1.5) => ({ stroke: `rgb(var(--${v}))`, strokeWidth: w, fill: "none" });

/**
 * Inline SVG illustration of the SolveX idea: a 10-K filing → verified shield → insight chart,
 * linked by a flowing dashed path. Colours come from theme variables so it suits light and dark.
 * Pure SVG (no image request); the floating motion is CSS transform-only.
 */
export function HeroArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 480 360" role="img" aria-label="Illustration: a financial filing is verified, shielded and turned into insight" className={className}>
      <defs>
        <linearGradient id="ha-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="rgb(var(--gold-400))" /><stop offset="1" stopColor="rgb(var(--gold-600))" />
        </linearGradient>
        <radialGradient id="ha-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="rgb(var(--navy-600))" stopOpacity=".35" /><stop offset="1" stopColor="rgb(var(--navy-600))" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="240" cy="180" r="170" fill="url(#ha-glow)" />
      <circle cx="240" cy="180" r="140" style={S("navy-200", 1)} strokeDasharray="2 7" />
      <circle cx="240" cy="180" r="100" style={S("navy-200", 1)} strokeDasharray="2 7" opacity=".7" />

      {/* flowing connector */}
      <path className="dash-flow" d="M150 120 C 210 90, 250 150, 300 170 S 340 250, 205 268" style={S("gold-500", 2)} strokeLinecap="round" />

      {/* filing document */}
      <g className="float-slow">
        <rect x="64" y="64" width="150" height="190" rx="14" style={{ ...S("navy-200", 1.5), fill: "rgb(var(--surface))" }} />
        <rect x="82" y="84" width="42" height="18" rx="9" style={F("brand")} />
        <text x="103" y="97" textAnchor="middle" fontSize="10" fontWeight="700" fill="#fff">10-K</text>
        {[124, 142, 160, 178].map((y, i) => <rect key={y} x="82" y={y} width={i % 2 ? 90 : 114} height="7" rx="3.5" style={F("navy-200")} />)}
        <rect x="82" y="204" width="114" height="34" rx="8" style={F("navy-50")} />
        <path d="M92 228 l12 -10 l10 6 l16 -14 l18 12" style={S("navy-600", 2.2)} strokeLinecap="round" strokeLinejoin="round" />
      </g>

      {/* verification shield */}
      <g className="float-slower">
        <path d="M300 96 l62 22 v52 c0 40 -26 66 -62 82 c-36 -16 -62 -42 -62 -82 v-52 z" style={{ fill: "rgb(var(--surface))", stroke: "url(#ha-g)", strokeWidth: 3 }} />
        <path d="M300 118 l42 15 v38 c0 28 -18 46 -42 58 c-24 -12 -42 -30 -42 -58 v-38 z" style={F("navy-50")} />
        <path d="M280 176 l15 15 l28 -31" style={{ stroke: "url(#ha-g)", strokeWidth: 8, fill: "none" }} strokeLinecap="round" strokeLinejoin="round" />
      </g>

      {/* insight chart */}
      <g className="float-slow" style={{ animationDelay: "-3s" }}>
        <rect x="316" y="236" width="128" height="86" rx="12" style={{ ...S("navy-200", 1.5), fill: "rgb(var(--surface))" }} />
        {[[334, 28], [356, 44], [378, 36], [400, 58], [422, 50]].map(([x, h], i) => (
          <rect key={x} x={x} y={304 - h} width="12" height={h} rx="3.5" style={F(i === 3 ? "gold-500" : "navy-600")} />
        ))}
      </g>

      {/* orbiting nodes */}
      <circle cx="150" cy="120" r="5" style={F("gold-500")} /><circle cx="205" cy="268" r="5" style={F("navy-600")} />
      <circle cx="420" cy="120" r="4" style={F("navy-600")} className="float-slower" /><circle cx="60" cy="300" r="4" style={F("gold-500")} className="float-slow" />
      <circle cx="440" cy="190" r="3" style={F("gold-500")} className="float-slow" />
    </svg>
  );
}
