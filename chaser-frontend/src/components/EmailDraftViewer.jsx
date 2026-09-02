import { Mail, ExternalLink, ShieldCheck, Copy, Check } from 'lucide-react'
import { useState } from 'react'

/**
 * Intelligently formats squashed or raw email text into professional structured email sections:
 * - Salutation / Greeting
 * - Body Paragraphs
 * - Actionable Payment CTA
 * - Professional Sign-off & Signature
 */
function parseEmailContent(text = '') {
  let raw = text.trim()

  // 1. Extract and format Salutation
  let salutation = ''
  const salutationMatch = raw.match(/^(Dear\s+[^,\n]+,|Hi\s+[^,\n]+,|Hello\s+[^,\n]+,|To whom it may concern,)/i)
  if (salutationMatch) {
    salutation = salutationMatch[1].trim()
    raw = raw.slice(salutationMatch[0].length).trim()
  }

  // 2. Extract and format Sign-off & Signature
  let signoff = ''
  let signoffSender = ''
  const signoffMatch = raw.match(/(Regards,|Best regards,|Sincerely,|Warm regards,|Thanks & regards,)\s*(.*)$/i)
  if (signoffMatch) {
    signoff = signoffMatch[1].trim()
    signoffSender = signoffMatch[2]?.trim() || 'Accounts Receivable Team'
    raw = raw.slice(0, signoffMatch.index).trim()
  }

  // 3. Clean up the body text into paragraphs
  // If the body already has explicit double newlines, split on them
  let paragraphs = []
  if (raw.includes('\n\n')) {
    paragraphs = raw.split(/\n\n+/).map((p) => p.trim()).filter(Boolean)
  } else if (raw.includes('\n')) {
    paragraphs = raw.split(/\n+/).map((p) => p.trim()).filter(Boolean)
  } else {
    // If squashed into one long block, intelligently split on sentences or key markers
    // e.g. "Given your history...", "You can complete the payment...", "Please let us know..."
    const sentenceSplit = raw.split(/(?<=[.!?])\s+(?=[A-Z])/)
    
    // Group into logical paragraphs (2-3 sentences each, or isolate payment instructions)
    let current = []
    for (const s of sentenceSplit) {
      if (s.toLowerCase().includes('http') || s.toLowerCase().includes('payment directly') || s.toLowerCase().includes('payment link')) {
        if (current.length > 0) {
          paragraphs.push(current.join(' '))
          current = []
        }
        paragraphs.push(s)
      } else {
        current.push(s)
        if (current.length >= 2) {
          paragraphs.push(current.join(' '))
          current = []
        }
      }
    }
    if (current.length > 0) {
      paragraphs.push(current.join(' '))
    }
  }

  return {
    salutation,
    paragraphs: paragraphs.length > 0 ? paragraphs : [raw],
    signoff,
    signoffSender,
  }
}

export default function EmailDraftViewer({ draft, customerId }) {
  const [copiedLink, setCopiedLink] = useState(false)
  const { salutation, paragraphs, signoff, signoffSender } = parseEmailContent(
    draft.body
  )

  const handleCopyLink = () => {
    if (!draft.payment_link) return
    navigator.clipboard.writeText(draft.payment_link)
    setCopiedLink(true)
    setTimeout(() => setCopiedLink(false), 2000)
  }

  const toneBadgeStyles = {
    urgent: 'bg-[var(--color-risk-high-bg)] text-[var(--color-risk-high)] border-[var(--color-risk-high-border)]',
    firm: 'bg-[var(--color-risk-med-bg)] text-[var(--color-risk-med)] border-[var(--color-risk-med-border)]',
    polite: 'bg-[var(--color-brass-100)] text-[var(--color-brass-700)] border-[var(--color-brass-200)]',
  }[draft.tone?.toLowerCase()] || 'bg-[var(--color-paper-dim)] text-[var(--color-ledger-700)] border-hairline'

  return (
    <div className="ledger-card rounded-lg border hairline overflow-hidden">
      {/* Email Client Header Bar */}
      <div className="bg-[var(--color-paper-dim)] px-5 py-3.5 border-b hairline flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded bg-[var(--color-brass-100)] border border-[var(--color-brass-200)] flex items-center justify-center text-[var(--color-brass-700)]">
            <Mail className="w-3.5 h-3.5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono-tab text-xs font-semibold text-[var(--color-ledger-900)]">
                Attempt #{draft.attempt_number}
              </span>
              <span className={`text-[10px] font-mono-tab px-2 py-0.5 rounded border uppercase font-semibold ${toneBadgeStyles}`}>
                {draft.tone} Tone
              </span>
              <span className="text-[10px] font-mono-tab px-2 py-0.5 rounded bg-[var(--color-paper-card)] border hairline text-[var(--color-ledger-500)] uppercase">
                {draft.channel}
              </span>
            </div>
          </div>
        </div>

        <div className="text-[11px] font-mono-tab text-[var(--color-ledger-400)]">
          Sent: {draft.sent_at}
        </div>
      </div>

      {/* Email Meta Fields (To, Subject, From) */}
      <div className="px-6 py-3 border-b hairline bg-[var(--color-paper-white)] text-xs font-mono-tab space-y-1.5">
        <div className="flex items-baseline gap-2">
          <span className="text-[var(--color-ledger-400)] w-14 shrink-0 uppercase text-[10px]">Subject:</span>
          <span className="font-sans font-semibold text-[var(--color-ledger-900)] text-sm">
            {draft.subject}
          </span>
        </div>
        <div className="flex items-baseline gap-2 text-[11px]">
          <span className="text-[var(--color-ledger-400)] w-14 shrink-0 uppercase text-[10px]">To:</span>
          <span className="text-[var(--color-ledger-700)]">
            {customerId ? `${customerId} <finance@buyer-domain.com>` : 'Accounts Payable'}
          </span>
        </div>
        <div className="flex items-baseline gap-2 text-[11px]">
          <span className="text-[var(--color-ledger-400)] w-14 shrink-0 uppercase text-[10px]">From:</span>
          <span className="text-[var(--color-ledger-700)]">
            Chaser.Ai Autonomous Agent &lt;receivables@razorpay-chaser.internal&gt;
          </span>
        </div>
      </div>

      {/* Formatted Email Body */}
      <div className="p-6 bg-[var(--color-paper-card)] font-sans text-sm text-[var(--color-ledger-800)] leading-relaxed space-y-4">
        {/* Salutation */}
        {salutation && (
          <p className="font-medium text-[var(--color-ledger-900)]">
            {salutation}
          </p>
        )}

        {/* Paragraphs */}
        {paragraphs.map((para, idx) => (
          <p key={idx} className="text-[var(--color-ledger-700)] leading-relaxed">
            {para}
          </p>
        ))}

        {/* Payment CTA Callout Box if payment link exists */}
        {draft.payment_link && (
          <div className="my-5 p-4 rounded-lg bg-[var(--color-paper-dim)] border border-[var(--color-brass-200)] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-0.5">
              <div className="flex items-center gap-1.5 text-xs font-mono-tab font-semibold text-[var(--color-brass-700)]">
                <ShieldCheck className="w-4 h-4 text-[var(--color-brass-600)]" />
                <span>Verified Razorpay Payment Gateway</span>
              </div>
              <p className="text-xs text-[var(--color-ledger-500)] font-mono-tab">
                Instant clearance & automated ledger settlement
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={handleCopyLink}
                className="px-2.5 py-1.5 rounded bg-[var(--color-paper-card)] border hairline text-xs font-mono-tab text-[var(--color-ledger-700)] hover:text-[var(--color-ledger-900)] hover:bg-[var(--color-paper-white)] transition-colors flex items-center gap-1.5"
                title="Copy Link"
              >
                {copiedLink ? <Check className="w-3.5 h-3.5 text-[var(--color-risk-low)]" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedLink ? 'Copied' : 'Copy'}</span>
              </button>
              <a
                href={draft.payment_link}
                target="_blank"
                rel="noreferrer"
                className="px-4 py-1.5 rounded bg-[var(--color-ledger-900)] hover:bg-[var(--color-brass-600)] text-[var(--color-paper-white)] text-xs font-mono-tab font-medium transition-colors inline-flex items-center gap-1.5 shadow-sm"
              >
                <span>Pay Invoice Online</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        )}

        {/* Sign-off & Signature Block */}
        <div className="pt-3 border-t hairline space-y-0.5">
          <p className="text-[var(--color-ledger-700)]">{signoff || 'Regards,'}</p>
          <p className="font-semibold text-[var(--color-ledger-900)]">{signoffSender || 'Accounts Receivable Team'}</p>
          <p className="text-[11px] font-mono-tab text-[var(--color-ledger-400)]">
            Autonomous AR Orchestration via Chaser.Ai
          </p>
        </div>
      </div>
    </div>
  )
}
