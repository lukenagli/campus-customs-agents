import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AGENTS, isAgent, money } from './agents'
import { api, ApiError } from './api'
import { ApprovalsPanel, type SignedCheck } from './components/ApprovalsPanel'
import { CashRegister } from './components/CashRegister'
import { ConfirmDialog, type ConfirmRequest } from './components/ConfirmDialog'
import { LiveFeed } from './components/LiveFeed'
import { RunSummary } from './components/RunSummary'
import { StaffDesk, type AgentState, type Handoff } from './components/StaffDesk'
import { TicketBoard } from './components/TicketBoard'
import { API_URL, POLL_ACTIVE_MS, POLL_IDLE_MS } from './config'
import { useInterval } from './hooks'
import type { AgentKey, Approval, ApprovalsResponse, AuditEvent, CashResponse, Ticket, TicketSummary } from './types'

const idleStates = (): Record<AgentKey, AgentState> =>
  Object.fromEntries(Object.keys(AGENTS).map((k) => [k, { status: 'idle', doing: '', toolCalls: 0 }])) as Record<AgentKey, AgentState>

/** Replay one run's events into "who is doing what" for the staff cards. */
function deskState(run: AuditEvent[], live: boolean) {
  const states = idleStates()
  const handoffs: Handoff[] = []
  let active: AgentKey | null = null
  for (const e of run) {
    const a = e.agent
    if (!isAgent(a)) continue
    const s = states[a]
    switch (e.step_type) {
      case 'run_started': s.status = 'working'; s.doing = 'Reading the ticket'; active = a; break
      case 'model_call': s.status = 'working'; s.doing = 'Thinking it over'; active = a; break
      case 'tool_call': s.status = 'working'; s.doing = `Checking ${e.tool_name}`; s.toolCalls += 1; active = a; break
      case 'delegation_sent': {
        const to = String(e.tool_args?.to_agent ?? '')
        if (isAgent(to)) {
          s.status = 'waiting'; s.doing = `Waiting on ${AGENTS[to].name}`
          states[to].status = 'working'; states[to].doing = `Picked up a task from ${AGENTS[a].name}`
          handoffs.push({ from: a, to, id: e.id }); active = to
        }
        break
      }
      case 'delegation_returned': {
        s.status = 'done'; s.doing = 'Reported back'
        const back = String(e.tool_args?.returned_to ?? '')
        if (isAgent(back)) { states[back].status = 'working'; states[back].doing = `Reading ${AGENTS[a].name}'s report`; active = back }
        break
      }
      case 'final_answer':
        if (a === 'boss' && e.depth === 0) { s.status = 'done'; s.doing = 'Final call made'; active = null }
        break
      case 'error': s.doing = 'Hit a problem'; break
    }
  }
  return { states, handoffs, active: live ? active : null }
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [events, setEvents] = useState<AuditEvent[]>([])
  const latestId = useRef<number | null>(null)
  const [approvals, setApprovals] = useState<ApprovalsResponse | null>(null)
  const [cash, setCash] = useState<CashResponse | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [summary, setSummary] = useState<TicketSummary | null>(null)
  const [justResolved, setJustResolved] = useState<Set<number>>(new Set())
  const [starting, setStarting] = useState<number | null>(null)
  const [approver, setApprover] = useState('Luke')
  const [checkErrors, setCheckErrors] = useState<Record<number, string>>({})
  const [busyCheck, setBusyCheck] = useState<number | null>(null)
  const [signed, setSigned] = useState<SignedCheck[]>([])
  const [confirm, setConfirm] = useState<ConfirmRequest | null>(null)
  const [banner, setBanner] = useState<string | null>(null)
  const prevTickets = useRef<Map<number, Ticket>>(new Map())

  const refreshMoney = useCallback(async () => {
    const [a, c] = await Promise.all([api.approvals(), api.cash()])
    setApprovals(a)
    setCash(c)
  }, [])

  const tick = useCallback(async () => {
    try {
      const [ts, ev] = await Promise.all([api.tickets(), api.events(latestId.current)])
      if (ev.events.length) {
        const fresh = [...ev.events].reverse()
        latestId.current = fresh[fresh.length - 1].id
        setEvents((old) => [...old, ...fresh.filter((e) => !old.length || e.id > old[old.length - 1].id)])
      }
      // A ticket "just resolved" when its run has finished and it is resolved (stamp animation).
      const resolvedNow: number[] = []
      for (const t of ts) {
        const before = prevTickets.current.get(t.id)
        const wasDone = before && before.status === 'resolved' && !before.running
        if (before && !wasDone && t.status === 'resolved' && !t.running) resolvedNow.push(t.id)
      }
      prevTickets.current = new Map(ts.map((t) => [t.id, t]))
      setTickets(ts)
      if (resolvedNow.length) {
        setJustResolved((s) => new Set([...s, ...resolvedNow]))
        setTimeout(() => setJustResolved((s) => new Set([...s].filter((id) => !resolvedNow.includes(id)))), 2500)
      }
      await refreshMoney()
      setBanner(null)
    } catch (err) {
      setBanner(err instanceof Error ? err.message : String(err))
    }
  }, [refreshMoney])

  useEffect(() => { void tick() }, [tick])
  const anyRunning = tickets.some((t) => t.running) || starting != null
  useInterval(tick, anyRunning ? POLL_ACTIVE_MS : POLL_IDLE_MS)

  useEffect(() => {
    if (selectedId == null && tickets.length) setSelectedId((tickets.find((t) => t.running) ?? tickets[0]).id)
  }, [tickets, selectedId])

  // Only show what happened since the last database reset.
  const lastResetId = useMemo(
    () => events.reduce((m, e) => (e.step_type === 'database_reset' ? e.id : m), -1), [events])
  const ticketEvents = useMemo(
    () => events.filter((e) => e.id > lastResetId && e.ticket_id === selectedId), [events, lastResetId, selectedId])
  const latestRunId = useMemo(
    () => [...ticketEvents].reverse().find((e) => e.step_type === 'run_started')?.run_id ?? null, [ticketEvents])
  const selected = tickets.find((t) => t.id === selectedId) ?? null
  const live = !!selected?.running
  const desk = useMemo(
    () => deskState(ticketEvents.filter((e) => e.run_id === latestRunId), live), [ticketEvents, latestRunId, live])

  // Shift report: after a finished run (since the last reset) for the selected ticket.
  useEffect(() => {
    if (selectedId == null || !latestRunId || live) { setSummary(null); return }
    let cancelled = false
    api.summary(selectedId)
      .then((s) => { if (!cancelled && s.run_id === latestRunId) setSummary(s) })
      .catch(() => { if (!cancelled) setSummary(null) })
    return () => { cancelled = true }
  }, [selectedId, latestRunId, live])

  const runTicket = async (id: number) => {
    setSelectedId(id)
    setStarting(id)
    setSummary(null)
    try {
      await api.run(id)
    } catch (err) {
      setBanner(err instanceof ApiError ? err.message : String(err))
    } finally {
      await tick()
      setStarting(null)
    }
  }

  const balance = cash?.checking_balance ?? 0

  const approve = (a: Approval) => {
    const name = approver.trim()
    setConfirm({
      title: `Sign check No. ${String(a.id).padStart(4, '0')}?`,
      body: (
        <>
          <p>Pay <b>{money(a.amount)}</b> to <b>{a.payee}</b> for {a.memo ?? a.reason}.</p>
          <p>Checking goes from <b>{money(balance)}</b> to <b>{money(balance - a.amount)}</b>.</p>
          <p className="muted">Signed by <b>{name}</b>. This moves real money in the shop's books.</p>
        </>
      ),
      confirmLabel: `Sign & pay ${money(a.amount)}`,
      onConfirm: async () => {
        setBusyCheck(a.id)
        setCheckErrors(({ [a.id]: _, ...rest }) => rest)
        try {
          await api.approve(a.id, name)
          setSigned((s) => [{ ...a, signedBy: name, outcome: 'paid' }, ...s])
        } catch (err) {
          setCheckErrors((e) => ({ ...e, [a.id]: err instanceof Error ? err.message : String(err) }))
        } finally {
          setBusyCheck(null)
          await tick()
        }
      },
    })
  }

  const reject = (a: Approval) => {
    const name = approver.trim()
    setConfirm({
      title: `Void check No. ${String(a.id).padStart(4, '0')}?`,
      body: <p>The {money(a.amount)} request to {a.payee} will be rejected. No money moves.</p>,
      confirmLabel: 'Void check',
      danger: true,
      input: { label: 'Reason', placeholder: 'e.g. Pay next week instead' },
      onConfirm: async (reason) => {
        setBusyCheck(a.id)
        try {
          await api.reject(a.id, name, reason)
          setSigned((s) => [{ ...a, signedBy: name, outcome: 'void' }, ...s])
        } catch (err) {
          setCheckErrors((e) => ({ ...e, [a.id]: err instanceof Error ? err.message : String(err) }))
        } finally {
          setBusyCheck(null)
          await tick()
        }
      },
    })
  }

  const reset = () => setConfirm({
    title: 'Reset the shop?',
    body: <p>This recopies the original database: cash back to $3,400, all tickets open, every request and payment
      cleared. The audit trail is kept (with a reset marker).</p>,
    confirmLabel: 'Reset database',
    danger: true,
    onConfirm: async () => {
      try {
        await api.reset()
        setSigned([]); setCheckErrors({}); setSummary(null); setJustResolved(new Set())
      } catch (err) {
        setBanner(err instanceof Error ? err.message : String(err))
      }
      await tick()
    },
  })

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="crest" aria-hidden="true">CC</span>
          <div>
            <h1>Campus Customs</h1>
            <p>Back counter · multi-agent operations{cash ? ` · shop date ${cash.today}` : ''}</p>
          </div>
        </div>
        <button className="btn btn-reset" onClick={reset} disabled={anyRunning} data-testid="reset">
          ↺ Reset shop
        </button>
      </header>

      {banner && <div className="banner" role="alert">{banner} <small>({API_URL})</small></div>}

      <main className="layout">
        <div className="area-board">
          <TicketBoard tickets={tickets} selectedId={selectedId} justResolved={justResolved} starting={starting}
                       onSelect={setSelectedId} onRun={runTicket} />
        </div>
        <div className="area-desk">
          <StaffDesk states={desk.states} active={desk.active} handoffs={desk.handoffs} live={live} />
        </div>
        <div className="area-feed">
          <LiveFeed events={ticketEvents} ticketId={selectedId} live={live} />
          {summary && !live && <RunSummary summary={summary} />}
        </div>
        <aside className="area-side">
          <CashRegister cash={cash} />
          <ApprovalsPanel approvals={approvals?.approvals ?? []} signed={signed} balance={balance} approver={approver}
                          errors={checkErrors} busy={busyCheck} onApprover={setApprover} onApprove={approve}
                          onReject={reject} />
        </aside>
      </main>
      <ConfirmDialog req={confirm} onClose={() => setConfirm(null)} />
    </div>
  )
}
