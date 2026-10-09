import { AGENTS, isAgent, money } from '../agents'
import type { Approval } from '../types'

const ONES = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve',
  'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen']
const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']

function words(n: number): string {
  if (n === 0) return 'zero'
  if (n < 20) return ONES[n]
  if (n < 100) return TENS[Math.floor(n / 10)] + (n % 10 ? '-' + ONES[n % 10] : '')
  if (n < 1000) return ONES[Math.floor(n / 100)] + ' hundred' + (n % 100 ? ' ' + words(n % 100) : '')
  return words(Math.floor(n / 1000)) + ' thousand' + (n % 1000 ? ' ' + words(n % 1000) : '')
}

export function amountInWords(amount: number): string {
  const dollars = Math.floor(amount)
  const cents = Math.round((amount - dollars) * 100)
  const w = words(dollars)
  return `${w.charAt(0).toUpperCase()}${w.slice(1)} and ${String(cents).padStart(2, '0')}/100 dollars`
}

const KIND_LABEL: Record<Approval['kind'], string> = { invoice: 'Vendor invoice', rent: 'Rent', purchase_order: 'Purchase order' }

export interface SignedCheck extends Approval {
  signedBy: string
  outcome: 'paid' | 'void'
}

interface Props {
  approvals: Approval[]
  signed: SignedCheck[]
  balance: number
  approver: string
  errors: Record<number, string>
  busy: number | null
  onApprover: (name: string) => void
  onApprove: (a: Approval) => void
  onReject: (a: Approval) => void
}

function Check({ a, balance, signedBy, outcome, children }: {
  a: Approval; balance: number; signedBy?: string; outcome?: 'paid' | 'void'; children?: React.ReactNode
}) {
  const requester = isAgent(a.requested_by.toLowerCase()) ? AGENTS[a.requested_by.toLowerCase() as keyof typeof AGENTS] : null
  return (
    <article className={`check ${outcome ? `check-${outcome}` : ''}`} data-testid={`check-${a.id}`}>
      <header className="check-head">
        <span className="check-bank">CAMPUS CUSTOMS · OPERATING CHECKING</span>
        <span className="check-no">No. {String(a.id).padStart(4, '0')}</span>
      </header>
      <div className="check-meta">
        <span>{KIND_LABEL[a.kind]} · ticket #{a.ticket_id}{a.ticket_subject ? ` (${a.ticket_subject})` : ''}</span>
        <span>Date {a.created_on}</span>
      </div>
      <div className="check-pay">
        <span className="check-label">PAY TO THE<br />ORDER OF</span>
        <span className="check-payee">{a.payee ?? '—'}</span>
        <span className="check-amount">{money(a.amount)}</span>
      </div>
      <div className="check-words">{amountInWords(a.amount)}</div>
      <div className="check-memo">
        <span className="check-label">MEMO</span> {a.memo ?? a.reason}
        <div className="check-reason">“{a.reason}” — requested by{' '}
          <b style={{ color: requester?.color }}>{requester ? `${requester.icon} ${requester.name}` : a.requested_by}</b>
        </div>
      </div>
      {!outcome && (
        <div className={`check-after ${a.amount > balance ? 'text-danger' : ''}`}>
          Cash after signing: <b>{money(balance - a.amount)}</b>
        </div>
      )}
      {children}
      {outcome && (
        <>
          <div className="signature-line">
            <span className="signature signature-draw">{signedBy}</span>
          </div>
          <span className={`stamp stamp-in check-stamp ${outcome === 'void' ? 'stamp-void' : 'stamp-paid'}`}>
            {outcome === 'paid' ? 'PAID' : 'VOID'}
          </span>
        </>
      )}
    </article>
  )
}

export function ApprovalsPanel({ approvals, signed, balance, approver, errors, busy, onApprover, onApprove, onReject }: Props) {
  return (
    <section className="approvals" aria-label="Approvals">
      <h2 className="section-title">
        Checks to sign {approvals.length > 0 && <span className="count">{approvals.length}</span>}
      </h2>
      <label className="approver">
        Signing as
        <input value={approver} onChange={(e) => onApprover(e.target.value)} data-testid="approver-name"
               aria-label="Approver name" />
      </label>
      {approvals.length === 0 && signed.length === 0 && (
        <p className="empty">No checks waiting. Agents can only <i>request</i> payments. Nothing moves until you sign.</p>
      )}
      <div className="checks">
        {approvals.map((a) => {
          const tooLow = a.amount > balance
          return (
            <Check key={a.id} a={a} balance={balance}>
              <div className="signature-line">
                <span className="signature-hint">x ______________________ </span>
              </div>
              {tooLow && (
                <p className="check-warning" role="alert">
                  Can't sign: only {money(balance)} in checking, and this check is for {money(a.amount)}.
                  Cash can never go negative.
                </p>
              )}
              {errors[a.id] && <p className="check-error" role="alert" data-testid={`check-error-${a.id}`}>
                Refused by the register: {errors[a.id]}</p>}
              <div className="check-actions">
                <button className="btn btn-ghost" disabled={busy === a.id} onClick={() => onReject(a)}
                        data-testid={`reject-${a.id}`}>Void</button>
                <button className="btn btn-sign" disabled={tooLow || busy === a.id || !approver.trim()}
                        title={tooLow ? 'Not enough cash in checking' : undefined}
                        onClick={() => onApprove(a)} data-testid={`approve-${a.id}`}>
                  {busy === a.id ? 'Signing…' : `Sign as ${approver.trim() || '…'}`}
                </button>
              </div>
            </Check>
          )
        })}
        {signed.map((s) => (
          <Check key={`signed-${s.id}`} a={s} balance={balance} signedBy={s.signedBy} outcome={s.outcome} />
        ))}
      </div>
    </section>
  )
}
