import type { AgentKey } from './types'

export interface AgentMeta {
  key: AgentKey
  name: string
  role: string
  icon: string
  color: string
}

export const AGENTS: Record<AgentKey, AgentMeta> = {
  boss: { key: 'boss', name: 'Boss', role: 'Shop manager · routes tickets, makes the final call', icon: '👔', color: '#00356b' },
  inventory: { key: 'inventory', name: 'Inventory', role: 'Stockroom · stock, shortfalls, vendors', icon: '📦', color: '#2e7d4f' },
  accounting: { key: 'accounting', name: 'Accounting', role: 'Books · cash, invoices, margins', icon: '🧮', color: '#a8571a' },
  facilities: { key: 'facilities', name: 'Facilities', role: 'Shop space · leases and rent', icon: '🔑', color: '#6a4c9c' },
  customer_service: { key: 'customer_service', name: 'Customer Service', role: 'Front counter · drafts replies', icon: '💬', color: '#b83a64' },
}

export const SPECIALISTS: AgentKey[] = ['inventory', 'accounting', 'facilities', 'customer_service']

export const isAgent = (name: string): name is AgentKey => name in AGENTS

export const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export const TICKET_TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

export const STATUS_LABEL: Record<string, string> = {
  open: 'Open',
  in_progress: 'In progress',
  waiting_on_approval: 'Waiting on approval',
  waiting_on_restock: 'Waiting on restock',
  resolved: 'Resolved',
}
