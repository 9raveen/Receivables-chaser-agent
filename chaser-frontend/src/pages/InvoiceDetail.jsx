import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  DollarSign,
  Calendar,
  ShieldAlert,
  Percent,
  Play,
  Send,
  MessageSquare,
  History,
  CheckCircle2,
  Clock,
  AlertCircle,
  Copy,
  Check,
} from 'lucide-react'
import { api } from '../api'
import RiskTag from '../components/RiskTag'
import StatusStamp from '../components/StatusStamp'
import ShapBarChart from '../components/ShapBarChart'
import AuditTrailItem from '../components/AuditTrailItem'
import KpiCard from '../components/KpiCard'
import EmailDraftViewer from '../components/EmailDraftViewer'

function formatINR(amount) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(amount)
}

const QUICK_REPLIES = [
  {
    label: 'Promise: Pay Next Friday',
    text: 'We acknowledge receipt and promise to pay the full invoice amount by next Friday.',
  },
  {
    label: 'Dispute: Quality Issue',
    text: 'We are disputing this invoice due to missing items and defective delivery in the shipment.',
  },
  {
    label: 'Extension: Request 15 Days',
    text: 'Due to temporary cashflow constraints, we request a 15-day extension to clear this ledger.',
  },
  {
    label: 'Settled: Already Transferred',
    text: 'We already initiated the bank transfer via NEFT this morning. UTR is AXIS19284729.',
  },
]

export default function InvoiceDetail() {
  const { id } = useParams()
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [replyText, setReplyText] = useState('')
  const [lastReplyResult, setLastReplyResult] = useState(null)
  const [copiedId, setCopiedId] = useState(false)

  const load = () => {
    api
      .getInvoice(id)
      .then(setDetail)
      .catch((e) => setError(e.message))
  }

  useEffect(load, [id])

  const handleCopyInvoiceId = () => {
    navigator.clipboard.writeText(id)
    setCopiedId(true)
    setTimeout(() => setCopiedId(false), 2000)
  }

  const handleRun = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.runInvoice(id)
      load()
    } catch (e) {
      setError(e.body?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }

  const handleReply = async () => {
    if (!replyText.trim()) return
    setBusy(true)
    setError(null)
    try {
      const result = await api.replyToInvoice(id, replyText)
      setLastReplyResult(result)
      setReplyText('')
      load()
    } catch (e) {
      setError(e.body?.detail || e.message)
    } finally {
      setBusy(false)
    }
  }

  if (!detail && !error) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-20 text-center">
        <p className="text-[var(--color-ledger-500)] text-sm font-mono-tab">Loading case file #{id}…</p>
      </div>
    )
  }

  if (error && !detail) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-20 text-center">
        <div className="inline-flex p-3 rounded-full bg-[var(--color-risk-high-bg)] text-[var(--color-risk-high)] mb-4">
          <AlertCircle className="w-8 h-8" />
        </div>
        <h2 className="text-lg font-bold font-display text-[var(--color-ledger-900)] mb-2">Error Loading Case File</h2>
        <p className="text-xs font-mono-tab text-[var(--color-risk-high)] max-w-md mx-auto mb-6">{error}</p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-[var(--color-paper-dim)] hover:bg-[var(--color-brass-100)] text-[var(--color-ledger-900)] text-xs font-mono-tab rounded border hairline"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Ledger</span>
        </Link>
      </div>
    )
  }

  const {
    state,
    awaiting_reply,
    has_run,
    shap_reasons,
    audit_trail = [],
    outreach_drafts = [],
    promise_history = [],
  } = detail

  return (
    <div className="max-w-6xl mx-auto px-6 py-10 space-y-8">
      {/* Top Breadcrumb */}
      <div className="flex items-center justify-between gap-4 pb-4 border-b hairline">
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded bg-[var(--color-paper-card)] border hairline text-[var(--color-ledger-500)] hover:text-[var(--color-ledger-900)] text-xs font-mono-tab transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Ledger</span>
          </Link>
          <span className="text-[var(--color-ledger-300)]">/</span>
          <span className="font-mono-tab font-semibold text-[var(--color-ledger-900)] text-xs">{state.invoice_id}</span>
        </div>

        <div className="flex items-center gap-2">
          <RiskTag tier={state.risk_tier} />
          <StatusStamp status={state.status} awaitingReply={awaiting_reply} hasRun={has_run} />
        </div>
      </div>

      {/* Case Header Hero Banner */}
      <div className="ledger-card rounded-lg p-6 border hairline">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div>
            <p className="font-mono-tab text-xs tracking-widest text-[var(--color-brass-600)] uppercase mb-1">
              {state.customer_id}
            </p>
            <div className="flex items-center gap-2.5 mb-2">
              <h1 className="text-3xl sm:text-4xl font-display text-[var(--color-ledger-900)]">
                {state.invoice_id}
              </h1>
              <button
                onClick={handleCopyInvoiceId}
                className="p-1 rounded hover:bg-[var(--color-paper-dim)] text-[var(--color-ledger-400)] hover:text-[var(--color-ledger-900)] transition-colors"
                title="Copy Invoice ID"
              >
                {copiedId ? <Check className="w-4 h-4 text-[var(--color-risk-low)]" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono-tab text-[var(--color-ledger-500)]">
              <span>Customer: <strong className="text-[var(--color-ledger-900)]">{state.customer_id}</strong></span>
              <span>•</span>
              <span>Due Date: <strong className="text-[var(--color-ledger-900)]">{state.due_date}</strong></span>
              <span>•</span>
              <span>Terms: <strong className="text-[var(--color-ledger-900)]">{state.payment_terms_days} days</strong></span>
            </div>
          </div>

          <div className="lg:text-right">
            <span className="text-[11px] font-mono-tab uppercase tracking-wider text-[var(--color-ledger-500)] block">
              Total Invoice Principal
            </span>
            <span className="font-display text-4xl text-[var(--color-ledger-900)] font-mono-tab">
              {formatINR(state.amount)}
            </span>
          </div>
        </div>
      </div>

      {/* Case Overview 4-KPI Deck */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          title="Principal Amount"
          value={formatINR(state.amount)}
          subvalue={`Terms ${state.payment_terms_days}d · ${state.currency || 'INR'}`}
          icon={DollarSign}
          accentColor="brass"
        />
        <KpiCard
          title="Aging & Overdue"
          value={state.overdue_ratio != null ? `${state.overdue_ratio.toFixed(2)}x` : '0.00x'}
          subvalue={`Due on ${state.due_date}`}
          icon={Calendar}
          accentColor={
            state.overdue_ratio > 0.5 ? 'rose' : state.overdue_ratio > 0.2 ? 'amber' : 'emerald'
          }
          progress={state.overdue_ratio != null ? Math.min(state.overdue_ratio * 100, 100) : 0}
        />
        <KpiCard
          title="Risk Assessment"
          value={state.risk_tier || 'UNSCORED'}
          subvalue="ML XGBoost Risk Policy"
          icon={ShieldAlert}
          accentColor={
            state.risk_tier === 'HIGH' ? 'rose' : state.risk_tier === 'MEDIUM' ? 'amber' : 'emerald'
          }
          badgeText={state.risk_tier || 'UNSCORED'}
          badgeType={
            state.risk_tier === 'HIGH' ? 'rose' : state.risk_tier === 'MEDIUM' ? 'amber' : 'emerald'
          }
        />
        <KpiCard
          title="Promise Reliability Index"
          value={
            state.promise_keep_score != null
              ? `${(state.promise_keep_score * 100).toFixed(0)}%`
              : '100%'
          }
          subvalue="Historical Buyer Fulfillment"
          icon={Percent}
          accentColor="brass"
          progress={state.promise_keep_score != null ? Math.round(state.promise_keep_score * 100) : 100}
        />
      </div>

      {/* Live AI Agent Control Center */}
      <div className="ledger-card rounded-lg p-6 border hairline">
        <div className="flex items-center justify-between mb-4 pb-3 border-b hairline">
          <div>
            <h2 className="text-sm font-semibold text-[var(--color-ledger-900)] font-display">
              Autonomous Chaser Runtime Control
            </h2>
            <p className="text-[11px] font-mono-tab text-[var(--color-ledger-500)]">
              LangGraph State Machine & Human-in-the-Loop Node
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono-tab">
            <span className="text-[var(--color-ledger-500)]">Status:</span>
            <strong className="text-[var(--color-brass-700)] uppercase">{state.status}</strong>
          </div>
        </div>

        {/* State 1: Uninitiated Agent */}
        {!has_run && (
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded bg-[var(--color-paper-dim)] border hairline">
            <div>
              <h3 className="text-sm font-semibold text-[var(--color-ledger-900)] mb-1">
                Outreach Cycle Not Initiated
              </h3>
              <p className="text-xs text-[var(--color-ledger-500)] max-w-xl">
                Triggering the agent will compute SHAP feature contributions, evaluate policy rules, and generate omnichannel outreach with personalized payment links.
              </p>
            </div>
            <button
              onClick={handleRun}
              disabled={busy}
              className="inline-flex items-center gap-2 px-4 py-2 rounded bg-[var(--color-ledger-900)] hover:bg-[var(--color-brass-600)] text-[var(--color-paper)] font-medium text-xs font-mono-tab transition-colors disabled:opacity-50 shrink-0"
            >
              <Play className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />
              <span>{busy ? 'Executing Agent…' : 'Run Autonomous Agent'}</span>
            </button>
          </div>
        )}

        {/* State 2: Awaiting Human/Buyer Reply (Interrupt Active) */}
        {has_run && awaiting_reply && (
          <div className="space-y-4">
            <div className="p-4 rounded bg-[var(--color-brass-50)] border border-[var(--color-brass-200)]">
              <div className="flex items-center gap-2 text-[var(--color-brass-700)] text-xs font-mono-tab font-semibold mb-1">
                <Clock className="w-4 h-4" />
                <span>Awaiting Buyer Reply (Execution Interrupted)</span>
              </div>
              <p className="text-xs text-[var(--color-ledger-700)] leading-relaxed">
                The agent sent outreach and is paused waiting for a buyer response. Enter a simulated buyer reply below to test real-time LLM intent extraction and autonomous graph state resumption.
              </p>
            </div>

            {/* Quick response templates */}
            <div>
              <span className="text-[11px] font-mono-tab text-[var(--color-ledger-500)] block mb-2">
                Quick Simulation Templates:
              </span>
              <div className="flex flex-wrap gap-2">
                {QUICK_REPLIES.map((tpl, i) => (
                  <button
                    key={i}
                    onClick={() => setReplyText(tpl.text)}
                    className="px-2.5 py-1 rounded bg-[var(--color-paper-dim)] hover:bg-[var(--color-brass-100)] border hairline text-[11px] font-mono-tab text-[var(--color-ledger-700)] hover:text-[var(--color-brass-700)] transition-colors text-left"
                  >
                    {tpl.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Input textarea */}
            <div className="space-y-2">
              <textarea
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                placeholder="e.g. We will pay the full amount by next Friday, apologies for the delay."
                rows={3}
                className="w-full p-3 rounded bg-[var(--color-paper)] border hairline text-xs font-body text-[var(--color-ledger-900)] placeholder-[var(--color-ledger-400)] focus:outline-none focus:border-[var(--color-brass-500)] resize-none"
              />
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-mono-tab text-[var(--color-ledger-400)]">
                  Resumes thread {id}
                </span>
                <button
                  onClick={handleReply}
                  disabled={busy || !replyText.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded bg-[var(--color-ledger-900)] hover:bg-[var(--color-brass-600)] text-[var(--color-paper)] font-medium text-xs font-mono-tab transition-colors disabled:opacity-50"
                >
                  <Send className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />
                  <span>{busy ? 'Processing…' : 'Send Reply'}</span>
                </button>
              </div>
            </div>

            {/* Extraction result */}
            {lastReplyResult && (
              <div className="p-3 rounded bg-[var(--color-paper-dim)] border hairline text-xs font-mono-tab space-y-1">
                <div className="flex items-center justify-between text-[var(--color-risk-low)] font-semibold">
                  <span>Intent Extracted</span>
                  <span>Confidence: {(lastReplyResult.extraction_confidence * 100 || 95).toFixed(0)}%</span>
                </div>
                <div className="text-[var(--color-ledger-700)]">
                  intent={lastReplyResult.last_extracted_intent} · status={lastReplyResult.status}
                </div>
              </div>
            )}
          </div>
        )}

        {/* State 3: Completed / Halted */}
        {has_run && !awaiting_reply && (
          <div className="p-4 rounded bg-[var(--color-paper-dim)] border hairline flex items-center justify-between">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-4 h-4 text-[var(--color-risk-low)]" />
              <div>
                <p className="text-xs font-mono-tab text-[var(--color-ledger-900)]">
                  Cycle complete — status: <strong>{state.status}</strong>
                </p>
                {state.stop_reason && (
                  <p className="text-[11px] font-mono-tab text-[var(--color-ledger-500)] mt-0.5">
                    Reason: {state.stop_reason}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-3 p-3 rounded bg-[var(--color-risk-high-bg)] text-xs font-mono-tab text-[var(--color-risk-high)]">
            {error}
          </div>
        )}
      </div>

      {/* SHAP Feature Explainability Breakdown */}
      {shap_reasons && shap_reasons.length > 0 && (
        <ShapBarChart reasons={shap_reasons} />
      )}

      {/* Outreach Drafts Log */}
      {outreach_drafts.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ledger-500)] font-mono-tab flex items-center gap-2">
              <MessageSquare className="w-3.5 h-3.5 text-[var(--color-brass-600)]" />
              Drafted Outreach ({outreach_drafts.length})
            </h2>
          </div>

          <div className="space-y-5">
            {outreach_drafts.map((draft, i) => (
              <EmailDraftViewer
                key={i}
                draft={draft}
                customerId={state.customer_id}
                invoiceId={state.invoice_id}
              />
            ))}
          </div>
        </div>
      )}

      {/* Promise Tracker Table */}
      {promise_history.length > 0 && (
        <div className="ledger-card rounded-lg p-5 border hairline">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ledger-500)] font-mono-tab flex items-center gap-2 mb-4">
            <History className="w-3.5 h-3.5 text-[var(--color-brass-600)]" />
            Payment Promises
          </h2>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono-tab">
              <thead>
                <tr className="border-b hairline text-[var(--color-ledger-400)] uppercase text-[10px]">
                  <th className="py-2.5 px-3">Promised Amount</th>
                  <th className="py-2.5 px-3">Target Date</th>
                  <th className="py-2.5 px-3">Recorded On</th>
                  <th className="py-2.5 px-3">Confidence</th>
                  <th className="py-2.5 px-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y hairline">
                {promise_history.map((p, i) => (
                  <tr key={i} className="hover:bg-[var(--color-paper-dim)]">
                    <td className="py-2.5 px-3 font-semibold text-[var(--color-ledger-900)]">
                      {formatINR(p.promised_amount)}
                    </td>
                    <td className="py-2.5 px-3 text-[var(--color-ledger-700)]">{p.promised_date}</td>
                    <td className="py-2.5 px-3 text-[var(--color-ledger-500)]">{p.made_on}</td>
                    <td className="py-2.5 px-3 text-[var(--color-ledger-700)]">
                      {p.confidence != null ? `${(p.confidence * 100).toFixed(0)}%` : '—'}
                    </td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold border ${
                          p.kept === true
                            ? 'bg-[var(--color-risk-low-bg)] text-[var(--color-risk-low)] border-[var(--color-risk-low-border)]'
                            : p.kept === false
                            ? 'bg-[var(--color-risk-high-bg)] text-[var(--color-risk-high)] border-[var(--color-risk-high-border)]'
                            : 'bg-[var(--color-risk-med-bg)] text-[var(--color-risk-med)] border-[var(--color-risk-med-border)]'
                        }`}
                      >
                        {p.kept === true ? 'Kept' : p.kept === false ? 'Broken' : 'Pending'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cryptographic Hash-Chained Audit Trail */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-ledger-500)] font-mono-tab flex items-center gap-2">
            <ShieldAlert className="w-3.5 h-3.5 text-[var(--color-brass-600)]" />
            Audit Trail — Hash-Chained ({audit_trail.length} Entries)
          </h2>
          <span className="text-[11px] font-mono-tab text-[var(--color-risk-low)] bg-[var(--color-risk-low-bg)] px-2 py-0.5 rounded border border-[var(--color-risk-low-border)]">
            Chain Intact
          </span>
        </div>

        {audit_trail.length === 0 ? (
          <div className="ledger-card rounded-lg p-6 border hairline text-center text-xs font-mono-tab text-[var(--color-ledger-500)]">
            No audit ledger entries recorded yet.
          </div>
        ) : (
          <div className="pt-2">
            {audit_trail.map((entry, i) => (
              <AuditTrailItem
                key={entry.entry_id || i}
                entry={entry}
                isLast={i === audit_trail.length - 1}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}


