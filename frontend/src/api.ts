import { API_URL } from './config'
import type { ApprovalsResponse, CashResponse, EventsResponse, Ticket, TicketSummary } from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, `Can't reach the backend at ${API_URL}. Is uvicorn running?`)
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body)
    throw new ApiError(res.status, detail || `${res.status} ${res.statusText}`)
  }
  return body as T
}

export const api = {
  tickets: () => request<{ tickets: Ticket[] }>('/tickets').then((r) => r.tickets),
  run: (id: number) => request<{ run_id: string }>(`/tickets/${id}/run`, { method: 'POST' }),
  events: (since?: number | null, limit = 1000) =>
    request<EventsResponse>(`/events?limit=${limit}${since != null ? `&since=${since}` : ''}`),
  summary: (id: number) => request<TicketSummary>(`/tickets/${id}/summary`),
  approvals: () => request<ApprovalsResponse>('/approvals'),
  approve: (id: number, approvedBy: string) =>
    request<Record<string, unknown>>(`/approvals/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  reject: (id: number, approvedBy: string, reason: string) =>
    request<Record<string, unknown>>(`/approvals/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy, reason }),
    }),
  cash: () => request<CashResponse>('/cash'),
  reset: () => request<{ ok: boolean; checking_balance: number }>('/reset', { method: 'POST' }),
}
