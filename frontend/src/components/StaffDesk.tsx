import { useLayoutEffect, useRef, useState } from 'react'
import { AGENTS, SPECIALISTS } from '../agents'
import type { AgentKey } from '../types'

export interface AgentState {
  status: 'idle' | 'working' | 'waiting' | 'done'
  doing: string
  toolCalls: number
}

export interface Handoff {
  from: AgentKey
  to: AgentKey
  id: number
}

interface Props {
  states: Record<AgentKey, AgentState>
  active: AgentKey | null
  handoffs: Handoff[]
  live: boolean
}

type Point = { x: number; y: number }

export function StaffDesk({ states, active, handoffs, live }: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const cards = useRef<Partial<Record<AgentKey, HTMLDivElement | null>>>({})
  const [centers, setCenters] = useState<Partial<Record<AgentKey, Point>>>({})

  useLayoutEffect(() => {
    const measure = () => {
      const box = wrap.current?.getBoundingClientRect()
      if (!box) return
      const next: Partial<Record<AgentKey, Point>> = {}
      for (const [k, el] of Object.entries(cards.current)) {
        if (!el) continue
        const r = el.getBoundingClientRect()
        next[k as AgentKey] = { x: r.left - box.left + r.width / 2, y: r.top - box.top + r.height / 2 }
      }
      setCenters(next)
    }
    measure()
    const ro = new ResizeObserver(measure)
    if (wrap.current) ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [])

  const latest = handoffs[handoffs.length - 1]
  const seen = new Set<string>()
  const lines = handoffs.filter((h) => {
    const k = `${h.from}>${h.to}`
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })

  const card = (key: AgentKey) => {
    const a = AGENTS[key]
    const s = states[key]
    const isActive = active === key
    return (
      <div
        key={key}
        ref={(el) => { cards.current[key] = el }}
        className={`staff staff-${key} ${key === 'boss' ? 'staff-boss' : ''} ${isActive ? 'staff-active' : ''} staff-${s.status}`}
        style={{ ['--agent' as string]: a.color }}
        data-testid={`agent-${key}`}
        data-active={isActive}
      >
        <div className="staff-icon" aria-hidden="true">{a.icon}</div>
        <div className="staff-body">
          <div className="staff-name">
            {a.name}
            {key === 'boss' && <span className="staff-rank">Manager</span>}
          </div>
          <div className="staff-role">{a.role}</div>
          <div className="staff-doing" aria-live="polite">
            {s.status === 'idle' ? 'At the counter' : s.doing}
          </div>
        </div>
        {s.toolCalls > 0 && <span className="staff-count" title="Tool calls this run">{s.toolCalls}</span>}
      </div>
    )
  }

  return (
    <section className="desk" aria-label="Staff at the desk">
      <h2 className="section-title">The back counter {live && <span className="live-dot">LIVE</span>}</h2>
      <div className="desk-surface" ref={wrap}>
        <svg className="handoffs" aria-hidden="true">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
            </marker>
          </defs>
          {lines.map((h) => {
            const a = centers[h.from]
            const b = centers[h.to]
            if (!a || !b) return null
            const isLatest = latest && latest.from === h.from && latest.to === h.to
            const midX = (a.x + b.x) / 2
            const midY = Math.min(a.y, b.y) - 30
            const d = `M${a.x},${a.y} Q${midX},${midY} ${b.x},${b.y}`
            return (
              <g key={`${h.from}-${h.to}`} className={isLatest && live ? 'handoff handoff-live' : 'handoff'}
                 style={{ color: AGENTS[h.from].color }}>
                <path d={d} markerEnd="url(#arrow)" />
                {isLatest && live && (
                  <circle r="6" className="handoff-slip">
                    <animateMotion dur="1.4s" repeatCount="indefinite" path={d} />
                  </circle>
                )}
              </g>
            )
          })}
        </svg>
        <div className="desk-boss">{card('boss')}</div>
        <div className="desk-team">{SPECIALISTS.map(card)}</div>
      </div>
      {latest && (
        <p className="handoff-caption" data-testid="handoff-caption">
          Latest handoff: <b style={{ color: AGENTS[latest.from].color }}>{AGENTS[latest.from].name}</b> →{' '}
          <b style={{ color: AGENTS[latest.to].color }}>{AGENTS[latest.to].name}</b>
        </p>
      )}
    </section>
  )
}
