/**
 * The Super Sale "SS" monogram.
 *
 * This mirrors `public/favicon.svg` — the tab icon has to be a standalone file,
 * so the two are kept deliberately identical. Change one, change the other.
 */
export default function BrandMark({ className = 'h-9 w-9', title = 'Super Sale' }) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      role="img"
      aria-label={title}
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient id="brandmark-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#334155" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
      </defs>

      <rect width="64" height="64" rx="13" fill="url(#brandmark-bg)" />
      {/* Hairline ring: without it the tile vanishes against the near-black
          sign-in background, which shares the gradient's bottom stop. */}
      <rect x="0.75" y="0.75" width="62.5" height="62.5" rx="12.4" fill="none" stroke="rgba(255,255,255,0.16)" strokeWidth="1.5" />
      <text
        x="32"
        y="47"
        textAnchor="middle"
        fontFamily="Segoe UI, Helvetica, Arial, sans-serif"
        fontSize="44"
        fontWeight="700"
        letterSpacing="-4"
        fill="#ffffff"
      >
        S<tspan fill="#60a5fa">S</tspan>
      </text>
    </svg>
  )
}
