export type AgentKey = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: string
  notes: string | null
  created_at: string
  pending_approvals: number
  pending_amount: number
  running: boolean
  run_id: string | null
  last_run_status: string | null
}

export interface TokenUsage {
  input_tokens: number
  output_tokens: number
  total_tokens: number
  requests?: number | null
}

export type StepType =
  | 'run_started' | 'model_call' | 'tool_call' | 'tool_result'
  | 'delegation_sent' | 'delegation_returned' | 'final_answer' | 'error'
  | 'human_decision' | 'status_change' | 'database_reset'

export interface AuditEvent {
  id: number
  timestamp: string
  run_id: string
  ticket_id: number
  agent: string
  step_type: StepType
  tool_name: string | null
  tool_args: Record<string, unknown> | null
  result: string | null
  depth: number
  step_usage: TokenUsage | null
  run_usage: TokenUsage | null
}

export interface EventsResponse {
  count: number
  latest_id: number | null
  active_runs: Record<string, string>
  events: AuditEvent[]
}

export interface Approval {
  id: number
  ticket_id: number
  kind: 'invoice' | 'rent' | 'purchase_order'
  ref_id: number | null
  amount: number
  reason: string
  requested_by: string
  status: string
  created_on: string
  vendor_id: number | null
  sku: string | null
  size: string | null
  qty: number | null
  ticket_subject: string | null
  ticket_requester: string | null
  vendor_name: string | null
  payee: string | null
  memo: string | null
}

export interface ApprovalsResponse {
  checking_balance: number
  pending_total: number
  available_after_pending: number
  approvals: Approval[]
}

export interface Payment {
  id: number
  kind: string
  ref_id: number
  amount: number
  account: string
  paid_at: string
  approved_by: string
}

export interface CashResponse {
  today: string
  checking_balance: number
  payments: Payment[]
  total_paid: number
  pending_total: number
  available_after_pending: number
}

export interface AgentSummary {
  agent: AgentKey
  model_calls: number
  tokens: number
  tools_used: Record<string, number>
  handed_off_to: { to: AgentKey; task: string }[]
  received_from: AgentKey[]
  summary: string | null
}

export interface TicketSummary {
  ticket_id: number
  run_id: string
  status: string | null
  decision: { decision?: string; discount_decision?: string | null; final_status?: string } | null
  usage: TokenUsage | null
  agents: AgentSummary[]
}
