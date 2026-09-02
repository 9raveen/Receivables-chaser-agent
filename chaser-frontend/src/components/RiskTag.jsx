const TIER_CONFIG = {
  HIGH: {
    label: 'HIGH RISK',
    badge: 'bg-[var(--color-risk-high-bg)] text-[var(--color-risk-high)] border-[var(--color-risk-high-border)]',
    dot: 'bg-[var(--color-risk-high)]',
  },
  MEDIUM: {
    label: 'MED RISK',
    badge: 'bg-[var(--color-risk-med-bg)] text-[var(--color-risk-med)] border-[var(--color-risk-med-border)]',
    dot: 'bg-[var(--color-risk-med)]',
  },
  LOW: {
    label: 'LOW RISK',
    badge: 'bg-[var(--color-risk-low-bg)] text-[var(--color-risk-low)] border-[var(--color-risk-low-border)]',
    dot: 'bg-[var(--color-risk-low)]',
  },
}

export default function RiskTag({ tier, size = 'md' }) {
  const normalizedTier = tier?.toUpperCase()
  const config = TIER_CONFIG[normalizedTier]

  if (!config) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-mono-tab font-medium text-[var(--color-ledger-400)] bg-[var(--color-paper-dim)] border border-[var(--color-ledger-200)] rounded">
        UNSCORED
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono-tab font-semibold rounded border tracking-wide transition-colors ${config.badge} ${
        size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-0.5 text-xs'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${config.dot}`} />
      <span>{config.label}</span>
    </span>
  )
}

