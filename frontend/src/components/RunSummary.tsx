import { AGENTS, isAgent } from '../agents'
import type { TicketSummary } from '../types'

export function RunSummary({ summary }: { summary: TicketSummary }) {
  return (
    <section className="summary" aria-label="Run summary" data-testid="run-summary">
      <h2 className="section-title">
        Shift report · ticket #{summary.ticket_id}
        {summary.usage && <small> · {summary.usage.total_tokens.toLocaleString()} tokens, {summary.usage.requests} model calls</small>}
      </h2>
      <div className="summary-grid">
        {summary.agents.map((a) => {
          const meta = AGENTS[a.agent]
          return (
            <article key={a.agent} className="report" style={{ ['--agent' as string]: meta.color }}>
              <header>
                <span className="report-icon" aria-hidden="true">{meta.icon}</span>
                <b>{meta.name}</b>
                <small>{a.model_calls} model calls · {a.tokens.toLocaleString()} tokens</small>
              </header>
              <p>{a.summary ?? 'No summary recorded.'}</p>
              {Object.keys(a.tools_used).length > 0 && (
                <div className="chips">
                  {Object.entries(a.tools_used).map(([tool, n]) => (
                    <span key={tool} className="chip chip-tool">🔧 {tool}{n > 1 ? ` ×${n}` : ''}</span>
                  ))}
                </div>
              )}
              {a.handed_off_to.length > 0 && (
                <p className="report-handoff">
                  Handed off to{' '}
                  {a.handed_off_to.map((h, i) => (
                    <span key={i}>{i > 0 && ', '}<b style={{ color: isAgent(h.to) ? AGENTS[h.to].color : undefined }}>
                      {isAgent(h.to) ? AGENTS[h.to].name : h.to}</b></span>
                  ))}
                </p>
              )}
              {a.received_from.length > 0 && (
                <p className="report-handoff muted">Asked by {a.received_from.map((r) => AGENTS[r]?.name ?? r).join(', ')}</p>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
