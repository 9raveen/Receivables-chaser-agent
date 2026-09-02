import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import InvoiceDetail from './pages/InvoiceDetail'

function Nav() {
  const location = useLocation()
  const isDetail = location.pathname.startsWith('/invoice/')

  return (
    <header className="border-b hairline bg-[var(--color-paper)] sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        {/* Brand & Logo */}
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-baseline gap-1.5 group">
            <span className="font-display font-medium text-2xl text-[var(--color-ledger-900)] group-hover:text-[var(--color-brass-600)] transition-colors">
              Chaser<span className="text-[var(--color-brass-500)] italic">.Ai</span>
            </span>
          </Link>

          <nav className="hidden sm:flex items-center gap-1 pl-4 border-l hairline">
            <Link
              to="/"
              className={`px-2.5 py-1 rounded text-xs font-mono-tab transition-colors ${
                !isDetail
                  ? 'bg-[var(--color-paper-dim)] text-[var(--color-ledger-900)] font-semibold'
                  : 'text-[var(--color-ledger-500)] hover:text-[var(--color-ledger-900)]'
              }`}
            >
              Ledger
            </Link>
          </nav>
        </div>

        {/* Live Engine Status Badge */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 font-mono-tab text-[10px] tracking-widest text-[var(--color-brass-600)] uppercase">
            <span className="w-2 h-2 rounded-full bg-[var(--color-brass-500)] animate-pulse" />
            <span>Receivables Agent · Active Mode</span>
          </div>
        </div>
      </div>
    </header>
  )
}

function Footer() {
  return (
    <footer className="mt-20 border-t hairline bg-[var(--color-paper)] py-8">
      <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs font-mono-tab text-[var(--color-ledger-400)]">
        <div>
          <span>Chaser.Ai · Autonomous Receivables Intelligence & Ledger</span>
        </div>
        <div className="flex items-center gap-3">
          <span>Hash-Chained Audit Trail</span>
          <span>·</span>
          <span>SHAP Explainability</span>
        </div>
      </div>
    </footer>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-[var(--color-paper)] text-[var(--color-ledger-900)]">
        <Nav />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/invoice/:id" element={<InvoiceDetail />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}


