import { useEffect, useRef } from 'react'
import { AGENTS, isAgent, money } from '../agents'
import type { AuditEvent } from '../types'

/** Pull a readable sentence out of a (possibly truncated) JSON final answer. */
export function extractSummary(result: string | null): string {
  if (!result) return ''
  try {
    const data = JSON.parse(result)
    return data.decision ?? data.summary ?? result
  } catch {
    const m = result.match(/"(?:decision|summary)":\s*"((?:[^"\\]|\\.)*)/)
    return m ? m[1].replace(/\\"/g, '"').replace(/\\u2014/g, '—').replace(/\.{3}$/, '') + (result.endsWith('...') ? '…' : '') : result
  }
}

function argText(args: Record<string, unknown> | null): string {
  if (!args) return ''
  return Object.entries(args)
    .filter(([k]) => k !== 'reason' && k !== 'note' && k !== 'draft' && k !== 'task')
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ')
}

function Tag({ agent }: { agent: string }) {
  const meta = isAgent(agent) ? AGENTS[agent] : null
  return (
    <span className="tag" style={{ ['--agent' as string]: meta?.color ?? '#555' }}>
      {meta ? `${meta.icon} ${meta.name}` : agent === 'human' ? '✍ You' : '⚙ System'}
    </span>
  )
}

function Line({ e }: { e: AuditEvent }) {
  const color = isAgent(e.agent) ? AGENTS[e.agent].color : '#555'
  const style = { ['--agent' as string]: color }
  switch (e.step_type) {
    case 'run_started':
      return <li className="feed-divider">Ticket #{e.ticket_id} handed to the team</li>
    case 'model_call': {
      const said = e.result ?? ''
      if (!said || said.startsWith('calls:')) return null // the tool chips below show what it's doing
      return <li className="msg" style={style}><Tag agent={e.agent} /><p>{said}</p></li>
    }
    case 'tool_call':
      if (e.tool_name === 'delegate') return null // shown as a handoff message instead
      return (
        <li className="tool-row" style={style}>
          <span className="chip chip-tool" title={argText(e.tool_args)}>
            <span className="chip-name">🔧 {e.tool_name}</span><span className="chip-args">{argText(e.tool_args)}</span>
          </span>
        </li>
      )
    case 'tool_result': {
      if (e.tool_name === 'delegate') return null
      const refused = /"refused": true|"found": false|"ok": false/.test(e.result ?? '')
      return (
        <li className="tool-row" style={style}>
          <span className={`chip chip-result ${refused ? 'chip-refused' : ''}`} title={e.result ?? ''}>
            {refused ? '⛔' : '↩'} {e.tool_name} {refused ? 'refused' : 'data'}
          </span>
        </li>
      )
    }
    case 'delegation_sent': {
      const to = String(e.tool_args?.to_agent ?? '')
      return (
        <li className="handoff-msg" style={style}>
          <Tag agent={e.agent} /> <span className="arrow-word">hands off to</span> {isAgent(to) && <Tag agent={to} />}
          <p className="task-slip">“{String(e.tool_args?.task ?? '')}”</p>
        </li>
      )
    }
    case 'delegation_returned':
      return (
        <li className="msg msg-report" style={style}>
          <Tag agent={e.agent} /> <span className="arrow-word">reports back to</span>{' '}
          {isAgent(String(e.tool_args?.returned_to)) && <Tag agent={String(e.tool_args?.returned_to)} />}
          <p>{e.result}</p>
        </li>
      )
    case 'final_answer':
      if (e.agent !== 'boss' || e.depth > 0) return null // specialists' answers appear as "reports back"
      return (
        <li className="msg msg-final" style={style}>
          <Tag agent={e.agent} /> <span className="arrow-word">final call</span>
          <p>{extractSummary(e.result)}</p>
        </li>
      )
    case 'human_decision': {
      const ok = /"ok": true/.test(e.result ?? '')
      const who = String(e.tool_args?.approved_by ?? e.tool_args?.rejected_by ?? 'Someone')
      const amount = e.result?.match(/"amount": ([\d.]+)/)?.[1]
      const verb = e.tool_name === 'execute_payment' ? (ok ? 'approved and paid' : 'tried to approve') :
        ok ? 'rejected' : 'tried to reject'
      return (
        <li className={`msg msg-human ${ok ? '' : 'msg-refused'}`}>
          <Tag agent="human" />
          <p>{who} {verb} request #{String(e.tool_args?.request_id)}{amount ? ` (${money(Number(amount))})` : ''}
            {!ok && <> — <b>refused:</b> {e.result?.match(/"error": "([^"]*)/)?.[1]}</>}</p>
        </li>
      )
    }
    case 'status_change':
      return <li className="feed-divider">{e.result}</li>
    case 'error':
      return <li className="msg msg-error" style={style}><Tag agent={e.agent} /><p>⚠ {e.result}</p></li>
    default:
      return null
  }
}

export function LiveFeed({ events, ticketId, live }: { events: AuditEvent[]; ticketId: number | null; live: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // Keep the newest event in view inside the feed box (never scrolls the page itself).
    const el = box.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: live ? 'smooth' : 'auto' })
  }, [events.length, ticketId, live])

  return (
    <section className="feed" aria-label="Shop floor conversation">
      <h2 className="section-title">Shop floor {ticketId != null && <small>· ticket #{ticketId}</small>}</h2>
      <div className="feed-scroll" data-testid="feed" ref={box}>
        {events.length === 0 ? (
          <p className="empty">Quiet counter. Pick a slip and hand it to the team to hear them work.</p>
        ) : (
          <ol className="feed-list">
            {events.map((e) => <Line key={e.id} e={e} />)}
          </ol>
        )}
      </div>
    </section>
  )
}
