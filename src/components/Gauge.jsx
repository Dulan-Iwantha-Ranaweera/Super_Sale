/**
 * Radial capacity gauge: a 270-degree arc drawn with stroke-dasharray so it
 * needs no chart library and stays crisp at any size.
 */
const RADIUS = 52
const STROKE = 10
const SIZE = (RADIUS + STROKE) * 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS
const ARC_FRACTION = 0.75

export default function Gauge({ percent = 0, label, caption, tone = 'amber' }) {
  const safePercent = Math.min(100, Math.max(0, Number(percent) || 0))
  const arcLength = CIRCUMFERENCE * ARC_FRACTION
  const valueLength = arcLength * (safePercent / 100)

  const strokeColor =
    tone === 'green'
      ? '#10b981'
      : tone === 'red'
        ? '#f43f5e'
        : tone === 'blue'
          ? '#3b82f6'
          : '#f59e0b'

  return (
    <div className="flex flex-col items-center text-center">
      <div className="relative" style={{ width: SIZE, height: SIZE }}>
        <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`${label}: ${safePercent}%`}>
          <g transform={`rotate(135 ${SIZE / 2} ${SIZE / 2})`}>
            <circle
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill="none"
              stroke="rgba(255,255,255,0.18)"
              strokeWidth={STROKE}
              strokeLinecap="round"
              strokeDasharray={`${arcLength} ${CIRCUMFERENCE}`}
            />
            <circle
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill="none"
              stroke={strokeColor}
              strokeWidth={STROKE}
              strokeLinecap="round"
              strokeDasharray={`${valueLength} ${CIRCUMFERENCE}`}
              style={{ transition: 'stroke-dasharray 600ms ease' }}
            />
          </g>
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-2xl font-semibold text-white">{Math.round(safePercent)}%</span>
        </div>
      </div>
      <p className="mt-1 text-sm font-medium text-slate-200">{label}</p>
      {caption ? <p className="text-xs text-slate-400">{caption}</p> : null}
    </div>
  )
}
