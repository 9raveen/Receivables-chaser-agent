import { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  DollarSign,
  AlertTriangle,
  Radio,
  CheckCircle2,
  Search,
  Download,
  RefreshCw,
  ArrowUpDown,
  Layers,
  ChevronRight,
  ShieldAlert,
} from 'lucide-react'
import { api } from '../api'
import RiskTag from '../components/RiskTag'
import StatusStamp from '../components/StatusStamp'
import KpiCard from '../components/KpiCard'

function formatINR(amount) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount)
}

export default function Dashboard() {
  const [invoices, setInvoices] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [activeTab, setActiveTab] = useState('ALL')
  const [sortBy, setSortBy] = useState('amount_desc')

  const fetchLedger = () => {
    setError(null)
    api
      .listInvoices()
      .then((data) => {
        setInvoices(data)
        setLoading(false)
      })
      .catch((e) => {
        setError(e.message)
        setLoading(false)
      })
  }

  useEffect(() => {
    let isMounted = true
    api
      .listInvoices()
      .then((data) => {
        if (isMounted) {
          setInvoices(data)
          setLoading(false)
        }
      })
      .catch((e) => {
        if (isMounted) {
          setError(e.message)
          setLoading(false)
        }
      })
    return () => {
      isMounted = false
    }
  }, [])

  const filteredInvoices = useMemo(() => {
    if (!invoices) return []

    return invoices
      .filter((inv) => {
        const matchesSearch =
          inv.invoice_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
          inv.customer_id.toLowerCase().includes(searchTerm.toLowerCase())

        if (!matchesSearch) return false

        if (activeTab === 'AWAITING') return inv.awaiting_reply
        if (activeTab === 'HIGH_RISK') return inv.risk_tier === 'HIGH'
        if (activeTab === 'ACTIVE') return inv.status === 'active'
        if (activeTab === 'RESOLVED') return inv.status === 'resolved' || inv.status === 'paid'

        return true
      })
      .sort((a, b) => {
        if (sortBy === 'amount_desc') return b.amount - a.amount
        if (sortBy === 'amount_asc') return a.amount - b.amount
        if (sortBy === 'overdue_desc') return (b.overdue_ratio || 0) - (a.overdue_ratio || 0)
        if (sortBy === 'risk_desc') {
          const rank = { HIGH: 3, MEDIUM: 2, LOW: 1 }
          return (rank[b.risk_tier] || 0) - (rank[a.risk_tier] || 0)
        }
        return 0
      })
  }, [invoices, searchTerm, activeTab, sortBy])

  const stats = useMemo(() => {
    if (!invoices) return null

    const totalOutstanding = invoices.reduce((sum, inv) => sum + inv.amount, 0)
    const awaitingReplyCount = invoices.filter((inv) => inv.awaiting_reply).length
    const awaitingReplyAmount = invoices
      .filter((inv) => inv.awaiting_reply)
      .reduce((sum, inv) => sum + inv.amount, 0)

    const highRiskInvoices = invoices.filter((inv) => inv.risk_tier === 'HIGH')
    const highRiskAmount = highRiskInvoices.reduce((sum, inv) => sum + inv.amount, 0)
    const highRiskPct = totalOutstanding > 0 ? (highRiskAmount / totalOutstanding) * 100 : 0

    const resolvedInvoices = invoices.filter(
      (inv) => inv.status === 'resolved' || inv.status === 'paid'
    )
    const resolvedAmount = resolvedInvoices.reduce((sum, inv) => sum + inv.amount, 0)
    const recoveryRate = totalOutstanding > 0 ? (resolvedAmount / totalOutstanding) * 100 : 0

    const medRiskAmount = invoices
      .filter((inv) => inv.risk_tier === 'MEDIUM')
      .reduce((sum, inv) => sum + inv.amount, 0)
    const lowRiskAmount = invoices
      .filter((inv) => inv.risk_tier === 'LOW')
      .reduce((sum, inv) => sum + inv.amount, 0)

    return {
      totalOutstanding,
      totalCount: invoices.length,
      awaitingReplyCount,
      awaitingReplyAmount,
      highRiskCount: highRiskInvoices.length,
      highRiskAmount,
      highRiskPct: highRiskPct.toFixed(1),
      resolvedCount: resolvedInvoices.length,
      resolvedAmount,
      recoveryRate: recoveryRate.toFixed(1),
      medRiskAmount,
      lowRiskAmount,
    }
  }, [invoices])

  const handleExportCSV = () => {
    if (!filteredInvoices || filteredInvoices.length === 0) return
    const headers = ['Invoice ID', 'Customer ID', 'Amount (INR)', 'Risk Tier', 'Overdue Ratio', 'Status', 'Awaiting Reply']
    const rows = filteredInvoices.map((inv) => [
      inv.invoice_id,
      inv.customer_id,
      inv.amount,
      inv.risk_tier || 'UNSCORED',
      inv.overdue_ratio ?? '',
      inv.status,
      inv.awaiting_reply ? 'YES' : 'NO',
    ])
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers, ...rows].map((e) => e.join(',')).join('\n')
    const encodedUri = encodeURI(csvContent)
    const link = document.createElement('a')
    link.setAttribute('href', encodedUri)
    link.setAttribute('download', `ChaserAI_Ledger_${new Date().toISOString().slice(0, 10)}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  if (error && !invoices) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-20 text-center">
        <div className="inline-flex p-3 rounded-full bg-[var(--color-risk-high-bg)] text-[var(--color-risk-high)] mb-4">
          <AlertTriangle className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold font-display text-[var(--color-ledger-900)] mb-2">
          Unable to Connect to Agent Backend
        </h2>
        <p className="text-sm font-mono-tab text-[var(--color-ledger-500)] max-w-md mx-auto mb-6">
          {error}
        </p>
        <button
          onClick={fetchLedger}
          className="inline-flex items-center gap-2 px-4 py-2 bg-[var(--color-ledger-900)] text-[var(--color-paper)] font-medium text-xs font-mono-tab rounded hover:bg-[var(--color-brass-600)] transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          <span>Retry Connection</span>
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-10 space-y-8">
      {/* Top Title & Toolbar */}
      <div className="flex flex-col md:flex-row md:items-baseline justify-between gap-4 pb-6 border-b hairline">
        <div>
          <p className="font-mono-tab text-xs tracking-widest text-[var(--color-brass-600)] uppercase mb-1">
            Receivables Ledger
          </p>
          <h1 className="font-display text-4xl text-[var(--color-ledger-900)] leading-tight">
            Financial Ledger & AI Chaser Console
          </h1>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchLedger}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono-tab rounded bg-[var(--color-paper-card)] border hairline text-[var(--color-ledger-700)] hover:text-[var(--color-ledger-900)] hover:border-[var(--color-ledger-300)] transition-all disabled:opacity-50"
            title="Refresh Ledger"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[var(--color-brass-600)]' : ''}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={handleExportCSV}
            disabled={!invoices || invoices.length === 0}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-mono-tab rounded bg-[var(--color-paper-card)] hover:bg-[var(--color-paper-dim)] text-[var(--color-brass-700)] border hairline font-medium transition-all"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* KPI Deck Grid */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            title="Total Outstanding"
            value={formatINR(stats.totalOutstanding)}
            subvalue={`${stats.totalCount} active invoice accounts`}
            icon={DollarSign}
            accentColor="brass"
            badgeText="PORTFOLIO BOOK"
            badgeType="brass"
          />
          <KpiCard
            title="High-Risk Exposure"
            value={formatINR(stats.highRiskAmount)}
            subvalue={`${stats.highRiskCount} invoices in critical tier`}
            icon={ShieldAlert}
            accentColor="rose"
            badgeText={`${stats.highRiskPct}% of Book`}
            badgeType="rose"
            progress={parseFloat(stats.highRiskPct)}
          />
          <KpiCard
            title="Awaiting Buyer Reply"
            value={stats.awaitingReplyCount}
            subvalue={formatINR(stats.awaitingReplyAmount) + ' awaiting response'}
            icon={Radio}
            accentColor="amber"
            badgeText="HITL QUEUE"
            badgeType="amber"
          />
          <KpiCard
            title="Recovered / Settled"
            value={stats.resolvedCount}
            subvalue={formatINR(stats.resolvedAmount) + ' collected'}
            icon={CheckCircle2}
            accentColor="emerald"
            badgeText={`${stats.recoveryRate}% Recovery`}
            badgeType="emerald"
            progress={parseFloat(stats.recoveryRate)}
          />
        </div>
      )}

      {/* Risk Distribution Portfolio Breakdown Bar */}
      {stats && stats.totalOutstanding > 0 && (
        <div className="ledger-card rounded-lg p-5 border hairline">
          <div className="flex items-center justify-between text-xs font-mono-tab mb-2">
            <span className="text-[var(--color-ledger-700)] font-semibold uppercase tracking-wider flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-[var(--color-brass-600)]" />
              Portfolio Risk Composition
            </span>
            <span className="text-[var(--color-ledger-500)]">Total Book: {formatINR(stats.totalOutstanding)}</span>
          </div>

          {/* Proportional bar */}
          <div className="w-full h-2.5 bg-[var(--color-paper-dim)] rounded-full overflow-hidden flex gap-0.5 p-0.5 border hairline">
            <div
              className="bg-[var(--color-risk-high)] rounded-l-full transition-all duration-500"
              style={{ width: `${(stats.highRiskAmount / stats.totalOutstanding) * 100}%` }}
              title={`High Risk: ${formatINR(stats.highRiskAmount)}`}
            />
            <div
              className="bg-[var(--color-risk-med)] transition-all duration-500"
              style={{ width: `${(stats.medRiskAmount / stats.totalOutstanding) * 100}%` }}
              title={`Medium Risk: ${formatINR(stats.medRiskAmount)}`}
            />
            <div
              className="bg-[var(--color-risk-low)] rounded-r-full transition-all duration-500"
              style={{ width: `${(stats.lowRiskAmount / stats.totalOutstanding) * 100}%` }}
              title={`Low Risk: ${formatINR(stats.lowRiskAmount)}`}
            />
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-6 mt-3 text-xs font-mono-tab">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[var(--color-risk-high)]" />
              <span className="text-[var(--color-ledger-500)]">High Risk:</span>
              <span className="text-[var(--color-ledger-900)] font-semibold">{formatINR(stats.highRiskAmount)}</span>
              <span className="text-[var(--color-ledger-400)]">
                ({((stats.highRiskAmount / stats.totalOutstanding) * 100).toFixed(0)}%)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[var(--color-risk-med)]" />
              <span className="text-[var(--color-ledger-500)]">Medium Risk:</span>
              <span className="text-[var(--color-ledger-900)] font-semibold">{formatINR(stats.medRiskAmount)}</span>
              <span className="text-[var(--color-ledger-400)]">
                ({((stats.medRiskAmount / stats.totalOutstanding) * 100).toFixed(0)}%)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[var(--color-risk-low)]" />
              <span className="text-[var(--color-ledger-500)]">Low Risk:</span>
              <span className="text-[var(--color-ledger-900)] font-semibold">{formatINR(stats.lowRiskAmount)}</span>
              <span className="text-[var(--color-ledger-400)]">
                ({((stats.lowRiskAmount / stats.totalOutstanding) * 100).toFixed(0)}%)
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Controls & Filter Toolbar */}
      <div className="ledger-card rounded-lg p-3.5 border hairline space-y-3">
        <div className="flex flex-col md:flex-row items-center justify-between gap-3">
          {/* Search Input */}
          <div className="relative w-full md:w-80">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-ledger-400)]" />
            <input
              type="text"
              placeholder="Search Invoice or Customer ID…"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded bg-[var(--color-paper)] border hairline text-xs font-mono-tab text-[var(--color-ledger-900)] placeholder-[var(--color-ledger-400)] focus:outline-none focus:border-[var(--color-brass-500)] transition-colors"
            />
          </div>

          {/* Quick Filter Tabs */}
          <div className="flex items-center gap-1 overflow-x-auto w-full md:w-auto pb-1 md:pb-0">
            {[
              { id: 'ALL', label: 'All Invoices' },
              { id: 'AWAITING', label: 'Awaiting Reply' },
              { id: 'HIGH_RISK', label: 'High Risk' },
              { id: 'ACTIVE', label: 'Active Chasing' },
              { id: 'RESOLVED', label: 'Resolved' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-1 rounded text-xs font-mono-tab font-medium whitespace-nowrap transition-all ${
                  activeTab === tab.id
                    ? 'bg-[var(--color-brass-100)] text-[var(--color-brass-700)] border border-[var(--color-brass-200)] font-semibold'
                    : 'text-[var(--color-ledger-500)] hover:text-[var(--color-ledger-900)] hover:bg-[var(--color-paper-dim)]'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Sort Selector */}
          <div className="flex items-center gap-2 w-full md:w-auto justify-end">
            <ArrowUpDown className="w-3.5 h-3.5 text-[var(--color-ledger-400)] shrink-0" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="bg-[var(--color-paper)] border hairline text-[var(--color-ledger-700)] text-xs font-mono-tab rounded px-2.5 py-1.5 focus:outline-none focus:border-[var(--color-brass-500)]"
            >
              <option value="amount_desc">Highest Amount (₹)</option>
              <option value="amount_asc">Lowest Amount (₹)</option>
              <option value="overdue_desc">Highest Overdue Ratio</option>
              <option value="risk_desc">Highest Risk Tier</option>
            </select>
          </div>
        </div>
      </div>

      {/* Ledger Table */}
      <div className="ledger-card rounded-lg border hairline overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="bg-[var(--color-paper-dim)] border-b hairline text-[var(--color-ledger-500)] uppercase font-mono-tab text-[11px] tracking-wider">
                <th className="py-3 px-4 font-medium">Invoice ID</th>
                <th className="py-3 px-4 font-medium">Customer</th>
                <th className="py-3 px-4 font-medium text-right">Amount</th>
                <th className="py-3 px-4 font-medium">Overdue Ratio</th>
                <th className="py-3 px-4 font-medium">Risk Tier</th>
                <th className="py-3 px-4 font-medium">Status</th>
                <th className="py-3 px-4 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y hairline">
              {loading && !invoices ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-[var(--color-ledger-500)] font-mono-tab text-xs">
                    <RefreshCw className="w-4 h-4 animate-spin mx-auto text-[var(--color-brass-600)] mb-2" />
                    Loading ledger data…
                  </td>
                </tr>
              ) : filteredInvoices.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-[var(--color-ledger-500)] font-mono-tab text-xs">
                    No invoices matching the selected criteria.
                  </td>
                </tr>
              ) : (
                filteredInvoices.map((inv) => (
                  <tr
                    key={inv.invoice_id}
                    className="hover:bg-[var(--color-paper-dim)] transition-colors group"
                  >
                    {/* Invoice ID */}
                    <td className="py-3.5 px-4">
                      <Link
                        to={`/invoice/${inv.invoice_id}`}
                        className="font-mono-tab font-semibold text-[var(--color-ledger-900)] hover:text-[var(--color-brass-600)] underline decoration-[var(--color-ledger-200)] underline-offset-2"
                      >
                        {inv.invoice_id}
                      </Link>
                    </td>

                    {/* Customer */}
                    <td className="py-3.5 px-4 font-mono-tab text-[var(--color-ledger-700)]">
                      {inv.customer_id}
                    </td>

                    {/* Amount */}
                    <td className="py-3.5 px-4 text-right font-mono-tab font-medium text-[var(--color-ledger-900)]">
                      {formatINR(inv.amount)}
                    </td>

                    {/* Overdue Ratio Meter */}
                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        <span className="font-mono-tab text-[var(--color-ledger-700)] text-xs w-10">
                          {inv.overdue_ratio != null ? inv.overdue_ratio.toFixed(2) : '—'}
                        </span>
                        {inv.overdue_ratio != null && (
                          <div className="w-16 bg-[var(--color-paper-dim)] rounded-full h-1.5 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                inv.overdue_ratio > 0.5
                                  ? 'bg-[var(--color-risk-high)]'
                                  : inv.overdue_ratio > 0.2
                                  ? 'bg-[var(--color-risk-med)]'
                                  : 'bg-[var(--color-risk-low)]'
                              }`}
                              style={{ width: `${Math.min(inv.overdue_ratio * 100, 100)}%` }}
                            />
                          </div>
                        )}
                      </div>
                    </td>

                    {/* Risk Tier Tag */}
                    <td className="py-3.5 px-4">
                      <RiskTag tier={inv.risk_tier} size="sm" />
                    </td>

                    {/* AI Agent Status */}
                    <td className="py-3.5 px-4">
                      <StatusStamp
                        status={inv.status}
                        awaitingReply={inv.awaiting_reply}
                        hasRun={inv.has_run}
                        size="sm"
                      />
                    </td>

                    {/* Action */}
                    <td className="py-3.5 px-4 text-right">
                      <Link
                        to={`/invoice/${inv.invoice_id}`}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-[var(--color-paper)] hover:bg-[var(--color-brass-100)] border hairline text-[var(--color-ledger-700)] hover:text-[var(--color-brass-700)] font-mono-tab text-[11px] transition-all"
                      >
                        <span>Case File</span>
                        <ChevronRight className="w-3 h-3" />
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Table Footer */}
        <div className="px-4 py-3 bg-[var(--color-paper-dim)] border-t hairline flex items-center justify-between text-xs font-mono-tab text-[var(--color-ledger-500)]">
          <div>
            Showing <strong className="text-[var(--color-ledger-900)]">{filteredInvoices.length}</strong> of{' '}
            <strong className="text-[var(--color-ledger-900)]">{invoices?.length || 0}</strong> invoices
          </div>
          <div>
            <span>Chaser.Ai Ledger Engine</span>
          </div>
        </div>
      </div>
    </div>
  )
}


