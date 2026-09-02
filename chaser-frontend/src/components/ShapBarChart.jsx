import { Sparkles, TrendingUp, TrendingDown } from 'lucide-react'

export default function ShapBarChart({ reasons = [] }) {
  if (!reasons || reasons.length === 0) {
    return (
      <div className="p-4 rounded bg-[var(--color-paper-dim)] border hairline text-center">
        <p className="text-xs text-[var(--color-ledger-500)] font-mono-tab">
          No SHAP explainability vector generated for this case.
        </p>
      </div>
    )
  }

  // Parse items like "feature_name: +0.250" or "feature_name: -0.150"
  const parsed = reasons.map((r) => {
    const parts = r.split(':')
    const feature = parts[0]?.trim() || r
    const valueStr = parts[1]?.trim() || '0'
    const value = parseFloat(valueStr) || 0
    return {
      raw: r,
      feature: feature.replace(/_/g, ' '),
      value,
      isPositive: value >= 0,
    }
  })

  const maxAbs = Math.max(...parsed.map((p) => Math.abs(p.value)), 0.01)

  return (
    <div className="ledger-card rounded-lg p-5 border hairline">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4 pb-3 border-b hairline">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded bg-[var(--color-brass-100)] text-[var(--color-brass-700)]">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[var(--color-ledger-900)] font-display">
              Decision Explainability (SHAP Attribution)
            </h3>
            <p className="text-[11px] text-[var(--color-ledger-500)] font-mono-tab">
              Feature contributions driving the autonomous risk & outreach policy
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono-tab">
          <div className="flex items-center gap-1.5 text-[var(--color-risk-high)]">
            <span className="w-2 h-2 rounded-full bg-[var(--color-risk-high)]" />
            <span>Elevates Risk</span>
          </div>
          <div className="flex items-center gap-1.5 text-[var(--color-risk-low)]">
            <span className="w-2 h-2 rounded-full bg-[var(--color-risk-low)]" />
            <span>Lowers Risk</span>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {parsed.map((item, idx) => {
          const percentage = Math.min(Math.round((Math.abs(item.value) / maxAbs) * 100), 100)
          return (
            <div key={idx}>
              <div className="flex items-center justify-between text-xs mb-1 font-mono-tab">
                <span className="text-[var(--color-ledger-700)] capitalize flex items-center gap-1.5">
                  {item.isPositive ? (
                    <TrendingUp className="w-3.5 h-3.5 text-[var(--color-risk-high)]" />
                  ) : (
                    <TrendingDown className="w-3.5 h-3.5 text-[var(--color-risk-low)]" />
                  )}
                  {item.feature}
                </span>
                <span
                  className={`font-semibold ${
                    item.isPositive ? 'text-[var(--color-risk-high)]' : 'text-[var(--color-risk-low)]'
                  }`}
                >
                  {item.value > 0 ? `+${item.value.toFixed(3)}` : item.value.toFixed(3)} SHAP
                </span>
              </div>

              {/* Horizontal bar */}
              <div className="w-full bg-[var(--color-paper-dim)] rounded-full h-1.5 overflow-hidden flex border hairline">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    item.isPositive ? 'bg-[var(--color-risk-high)]' : 'bg-[var(--color-risk-low)]'
                  }`}
                  style={{ width: `${Math.max(percentage, 8)}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

