import { useEffect, useRef, useState } from 'react'

/** Animates a number toward `target` (eased), so cash visibly counts down after a payment.
 *  The first real value (and any value after `null`) is shown immediately, not animated. */
export function useAnimatedNumber(target: number | null, durationMs = 1400): number | null {
  const [value, setValue] = useState(target)
  const from = useRef(target)
  const current = useRef(target)

  useEffect(() => {
    if (target == null || current.current == null) {
      current.current = target
      setValue(target)
      return
    }
    from.current = current.current
    if (from.current === target) return
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs)
      const eased = 1 - Math.pow(1 - t, 3)
      const next = from.current! + (target - from.current!) * eased
      current.current = next
      setValue(next)
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])

  return value
}

/** Runs `fn` every `ms` while mounted; `fn` always sees the latest closure. */
export function useInterval(fn: () => void, ms: number | null) {
  const saved = useRef(fn)
  useEffect(() => {
    saved.current = fn
  }, [fn])
  useEffect(() => {
    if (ms == null) return
    const id = setInterval(() => saved.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}
