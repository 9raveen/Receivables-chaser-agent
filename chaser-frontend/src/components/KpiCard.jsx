export default function KpiCard({
  title,
  value,
  subvalue,
  trend,
  trendPositive,
  icon: Icon,
  badgeText,
  badgeType = 'brass',
  accentColor = 'brass',
  progress,
  onClick,
}) {
  const accentClasses = {
    brass: 'bg-[var(--color-brass-500)]',
    rose: 'bg-[var(--color-risk-high)]',
    amber: 'bg-[var(--color-risk-med)]',
    emerald: 'bg-[var(--color-risk-low)]',
  }[accentColor] || 'bg-[var(--color-brass-500)]'

  const iconBgClasses = {
    brass: 'bg-[var(--color-brass-100)] text-[var(--color-brass-700)] border-[var(--color-brass-200)]',
    rose: 'bg-[var(--color-risk-high-bg)] text-[var(--color-risk-high)] border-[var(--color-risk-high-border)]',
    amber: 'bg-[var(--color-risk-med-bg)] text-[var(--color-risk-med)] border-[var(--color-risk-med-border)]',
    emerald: 'bg-[var(--color-risk-low-bg)] text-[var(--color-risk-low)] border-[var(--color-risk-low-border)]',
  }[accentColor] || 'bg-[var(--color-brass-100)] text-[var(--color-brass-700)]'

  return (
    <div
      onClick={onClick}
      className={`ledger-card ledger-card-hover rounded-lg p-5 relative overflow-hidden flex flex-col justify-between ${
        onClick ? 'cursor-pointer' : ''
      }`}
    >
      {/* Top subtle hairline accent bar */}
      <div className={`absolute top-0 left-0 right-0 h-[2px] ${accentClasses}`} />

      <div>
        {/* Header line with title and icon */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <span className="text-[11px] font-mono-tab font-semibold tracking-wider text-[var(--color-ledger-500)] uppercase">
            {title}
          </span>
          {Icon && (
            <div className={`p-1.5 rounded border ${iconBgClasses}`}>
              <Icon className="w-4 h-4" />
            </div>
          )}
        </div>

        {/* Main Value Display in Fraunces serif */}
        <div className="flex items-baseline gap-2 mb-1">
          <span className="font-display text-3xl font-medium tracking-tight text-[var(--color-ledger-900)]">
            {value}
          </span>
          {badgeText && (
            <span
              className={`text-[10px] font-mono-tab px-2 py-0.5 rounded font-semibold border ${
                badgeType === 'rose'
                  ? 'bg-[var(--color-risk-high-bg)] text-[var(--color-risk-high)] border-[var(--color-risk-high-border)]'
                  : badgeType === 'amber'
                  ? 'bg-[var(--color-risk-med-bg)] text-[var(--color-risk-med)] border-[var(--color-risk-med-border)]'
                  : badgeType === 'emerald'
                  ? 'bg-[var(--color-risk-low-bg)] text-[var(--color-risk-low)] border-[var(--color-risk-low-border)]'
                  : 'bg-[var(--color-brass-100)] text-[var(--color-brass-700)] border-[var(--color-brass-200)]'
              }`}
            >
              {badgeText}
            </span>
          )}
        </div>

        {/* Subtitle / context description */}
        {subvalue && (
          <p className="text-xs text-[var(--color-ledger-500)] font-sans mt-1 line-clamp-1">
            {subvalue}
          </p>
        )}
      </div>

      {/* Footer / Trend or Progress */}
      {(trend || progress !== undefined) && (
        <div className="mt-4 pt-3 border-t hairline flex items-center justify-between">
          {trend && (
            <div className="flex items-center gap-1.5 text-xs font-mono-tab">
              <span
                className={`font-semibold ${
                  trendPositive ? 'text-[var(--color-risk-low)]' : 'text-[var(--color-risk-high)]'
                }`}
              >
                {trend}
              </span>
              <span className="text-[var(--color-ledger-400)] text-[11px]">vs total book</span>
            </div>
          )}
          {progress !== undefined && (
            <div className="w-full flex items-center gap-2">
              <div className="flex-1 bg-[var(--color-paper-dim)] rounded-full h-1.5 overflow-hidden">
                <div
                  className={`h-full rounded-full ${accentClasses}`}
                  style={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }}
                />
              </div>
              <span className="text-[11px] font-mono-tab text-[var(--color-ledger-500)] font-medium shrink-0">
                {progress}%
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

