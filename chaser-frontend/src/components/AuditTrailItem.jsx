import { useState } from 'react'
import { Check, Copy, Hash, ShieldCheck, ChevronDown, ChevronRight, Activity } from 'lucide-react'

export default function AuditTrailItem({ entry, isLast }) {
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const handleCopyHash = (e) => {
    e.stopPropagation()
    navigator.clipboard.writeText(entry.this_hash)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex gap-4 group">
      {/* Hash chain connector column with signature brass dots */}
      <div className="flex flex-col items-center">
        <div className="w-2.5 h-2.5 rounded-full bg-[var(--color-brass-500)] mt-1.5 shrink-0" />
        {!isLast && <div className="chain-connector flex-1 my-1 min-h-[36px]" />}
      </div>

      {/* Entry Body Card */}
      <div className="pb-5 flex-1 min-w-0">
        <div
          onClick={() => setExpanded(!expanded)}
          className="ledger-card ledger-card-hover rounded-lg p-4 border hairline cursor-pointer"
        >
          {/* Header with Node, Decision & Hash */}
          <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono-tab text-xs font-semibold text-[var(--color-ledger-900)] px-2 py-0.5 rounded bg-[var(--color-paper-dim)] border hairline">
                {entry.node}
              </span>
              <span className="text-xs font-semibold text-[var(--color-brass-700)] font-mono-tab flex items-center gap-1">
                <Activity className="w-3.5 h-3.5 text-[var(--color-brass-500)]" />
                {entry.decision}
              </span>
            </div>

            {/* Cryptographic hash badge */}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleCopyHash}
                title="Copy Full SHA-256 Block Hash"
                className="inline-flex items-center gap-1 text-[11px] font-mono-tab px-2 py-0.5 rounded bg-[var(--color-paper-dim)] hover:bg-[var(--color-brass-100)] border hairline text-[var(--color-ledger-500)] hover:text-[var(--color-brass-700)] transition-colors"
              >
                <Hash className="w-3 h-3 text-[var(--color-brass-600)]" />
                <span>#{entry.this_hash?.slice(0, 8)}</span>
                {copied ? (
                  <Check className="w-3 h-3 text-[var(--color-risk-low)]" />
                ) : (
                  <Copy className="w-3 h-3 opacity-60" />
                )}
              </button>
              <div className="text-[var(--color-ledger-400)]">
                {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              </div>
            </div>
          </div>

          {/* Reason text */}
          <p className="text-sm text-[var(--color-ledger-700)] leading-relaxed font-sans">{entry.reason}</p>

          {/* Timestamp & Verification Footer */}
          <div className="flex items-center justify-between mt-3 pt-2 border-t hairline text-[11px] font-mono-tab text-[var(--color-ledger-400)]">
            <span className="flex items-center gap-1 text-[var(--color-risk-low)] font-medium">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Immutable Chain Verified</span>
            </span>
            <span>{entry.timestamp}</span>
          </div>

          {/* Expanded Cryptographic Detail */}
          {expanded && (
            <div className="mt-3 pt-3 border-t hairline space-y-2 text-xs font-mono-tab bg-[var(--color-paper-dim)] p-3 rounded border hairline">
              <div>
                <span className="text-[var(--color-ledger-400)] block text-[10px] uppercase tracking-wider">
                  Full Block Hash (SHA-256)
                </span>
                <span className="text-[var(--color-brass-700)] break-all text-[11px]">{entry.this_hash}</span>
              </div>
              {entry.prev_hash && (
                <div>
                  <span className="text-[var(--color-ledger-400)] block text-[10px] uppercase tracking-wider">
                    Parent Hash
                  </span>
                  <span className="text-[var(--color-ledger-500)] break-all text-[11px]">
                    {entry.prev_hash}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

