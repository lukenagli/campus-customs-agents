import { STATUS_LABEL, TICKET_TYPE_LABEL, money } from '../agents'
import type { Ticket } from '../types'

interface Props {
  tickets: Ticket[]
  selectedId: number | null
  justResolved: Set<number>
  starting: number | null
  onSelect: (id: number) => void
  onRun: (id: number) => void
}

const TILT = [-1.6, 1.1, -0.6]

function detail(t: Ticket): string {
  if (t.sku) return `${t.qty ?? '?'} × ${t.sku} · size ${t.size ?? '?'}`
  if (t.lease_id) return `Lease #${t.lease_id}`
  if (t.invoice_id) return `Invoice #${t.invoice_id}`
  return ''
}

export function TicketBoard({ tickets, selectedId, justResolved, starting, onSelect, onRun }: Props) {
  return (
    <section className="board" aria-label="Ticket board">
      <h2 className="section-title">Order board</h2>
      <div className="slips">
        {tickets.map((t, i) => {
          const selected = t.id === selectedId
          const busy = t.running || starting === t.id
          const resolved = t.status === 'resolved' && !busy // stamp only once the run has really finished
          return (
            <article
              key={t.id}
              className={`slip ${selected ? 'slip-selected' : ''} ${busy ? 'slip-busy' : ''}`}
              style={{ ['--tilt' as string]: `${TILT[i % TILT.length]}deg` }}
              onClick={() => onSelect(t.id)}
              data-testid={`ticket-${t.id}`}
              aria-current={selected}
            >
              <span className="pin" aria-hidden="true" />
              <header className="slip-head">
                <span className="slip-no">No. {t.id}</span>
                <span className="slip-type">{TICKET_TYPE_LABEL[t.type] ?? t.type}</span>
              </header>
              <h3 className="slip-subject">{t.subject}</h3>
              <p className="slip-line"><b>From</b> {t.requester}</p>
              {detail(t) && <p className="slip-line mono">{detail(t)}</p>}
              {t.notes && <p className="slip-note">“{t.notes}”</p>}
              <footer className="slip-foot">
                <span className={`status status-${t.status}`} data-testid={`status-${t.id}`}>
                  {busy ? 'Team working…' : STATUS_LABEL[t.status] ?? t.status}
                </span>
                {t.pending_approvals > 0 && (
                  <span className="badge-pending" title={`${money(t.pending_amount)} waiting for a signature`}>
                    approval pending
                  </span>
                )}
              </footer>
              {!resolved && (
                <button
                  className="btn btn-run"
                  disabled={busy}
                  onClick={(e) => {
                    e.stopPropagation()
                    onRun(t.id)
                  }}
                  data-testid={`run-${t.id}`}
                >
                  {busy ? <><span className="spinner" aria-hidden="true" /> Working</> : 'Hand to the team ▸'}
                </button>
              )}
              {resolved && (
                <span className={`stamp ${justResolved.has(t.id) ? 'stamp-in' : ''}`} aria-label="Resolved">
                  RESOLVED
                </span>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
