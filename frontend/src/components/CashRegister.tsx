import { money } from '../agents'
import { useAnimatedNumber } from '../hooks'
import type { CashResponse } from '../types'

export function CashRegister({ cash }: { cash: CashResponse | null }) {
  const balance = cash?.checking_balance ?? 0
  const pending = cash?.pending_total ?? 0
  const shown = useAnimatedNumber(cash ? balance : null)
  const dropping = shown != null && Math.abs(shown - balance) > 0.5

  const pendingPct = balance > 0 ? Math.min(100, (pending / balance) * 100) : pending > 0 ? 100 : 0
  const short = pending > balance

  return (
    <section className="register" aria-label="Cash register">
      <div className="register-top">
        <span className="register-brand">CC · REGISTER 1</span>
        <span className="register-date">shop date {cash?.today ?? '—'}</span>
      </div>
      <div className={`lcd ${dropping ? 'lcd-dropping' : ''}`} aria-live="polite">
        <span className="lcd-label">CHECKING</span>
        <span className="lcd-value" data-testid="cash-balance" data-value={balance.toFixed(2)}>
          {money(shown)}
        </span>
      </div>
      <div className="owed">
        <div className="owed-bar" role="img"
             aria-label={`Pending approvals ${money(pending)} of ${money(balance)} cash`}>
          <div className={`owed-fill ${short ? 'owed-short' : ''}`} style={{ width: `${pendingPct}%` }} />
        </div>
        <div className="owed-legend">
          <span><i className="dot dot-pending" /> Pending approvals {money(pending)}</span>
          <span className={short ? 'text-danger' : ''}>
            After: {money(balance - pending)}
          </span>
        </div>
      </div>
      {cash && cash.payments.length > 0 && (
        <ul className="tape" aria-label="Payments made">
          {cash.payments.map((p) => (
            <li key={p.id}>
              <span>#{p.id} {p.kind.replace('_', ' ')}</span>
              <span>−{money(p.amount)}</span>
              <span className="tape-who">✍ {p.approved_by}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
