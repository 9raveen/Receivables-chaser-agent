const LABELS = {
  active: 'Active Chasing',
  resolved: 'Resolved',
  paid: 'Paid / Settled',
  promised: 'Promise Active',
  exception: 'Exception',
  exhausted: 'Exhausted',
  disputed: 'Disputed',
}

export default function StatusStamp({ status, awaitingReply, hasRun, size = 'md' }) {
  if (!hasRun) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 font-mono-tab text-[var(--color-ledger-400)] ${
          size === 'sm' ? 'text-[11px]' : 'text-xs'
        }`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-ledger-300)]" />
        <span>Not contacted</span>
      </span>
    )
  }

  if (awaitingReply) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 font-mono-tab font-medium text-[var(--color-brass-700)] bg-[var(--color-brass-100)] px-2 py-0.5 rounded border border-[var(--color-brass-200)] ${
          size === 'sm' ? 'text-[10px]' : 'text-xs'
        }`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-brass-600)] animate-pulse" />
        <span>Awaiting reply</span>
      </span>
    )
  }

  const isProblem = status === 'exception' || status === 'exhausted' || status === 'disputed'
  const isGood = status === 'resolved' || status === 'paid'

  const dotColor = isProblem
    ? 'bg-[var(--color-risk-high)]'
    : isGood
      ? 'bg-[var(--color-risk-low)]'
      : 'bg-[var(--color-brass-600)]'

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono-tab text-[var(--color-ledger-700)] ${
        size === 'sm' ? 'text-[11px]' : 'text-xs'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
      <span>{LABELS[status] || status}</span>
    </span>
  )
}


