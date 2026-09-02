const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const body = await res.json()
  if (!res.ok) {
    const err = new Error(body.detail || 'Request failed')
    err.status = res.status
    err.body = body
    throw err
  }
  return body
}

export const api = {
  listInvoices: () => request('/api/invoices'),
  getInvoice: (id) => request(`/api/invoices/${id}`),
  runInvoice: (id) => request(`/api/invoices/${id}/run`, { method: 'POST' }),
  replyToInvoice: (id, replyText) =>
    request(`/api/invoices/${id}/reply`, {
      method: 'POST',
      body: JSON.stringify({ reply_text: replyText }),
    }),
}
