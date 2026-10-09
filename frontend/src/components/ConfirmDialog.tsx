import { useEffect, useRef, useState } from 'react'

export interface ConfirmRequest {
  title: string
  body: React.ReactNode
  confirmLabel: string
  danger?: boolean
  input?: { label: string; placeholder?: string }
  onConfirm: (input: string) => void
}

export function ConfirmDialog({ req, onClose }: { req: ConfirmRequest | null; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [text, setText] = useState('')

  useEffect(() => {
    const d = dialog.current
    if (!d) return
    if (req) {
      setText('')
      if (!d.open) d.showModal()
    } else if (d.open) d.close()
  }, [req])

  const needsInput = !!req?.input
  return (
    <dialog ref={dialog} className="confirm" onClose={onClose} data-testid="confirm-dialog">
      {req && (
        <form method="dialog" onSubmit={(e) => {
          e.preventDefault()
          if (needsInput && !text.trim()) return
          req.onConfirm(text.trim())
          onClose()
        }}>
          <h3>{req.title}</h3>
          <div className="confirm-body">{req.body}</div>
          {req.input && (
            <label className="confirm-input">
              {req.input.label}
              <input autoFocus value={text} placeholder={req.input.placeholder}
                     onChange={(e) => setText(e.target.value)} />
            </label>
          )}
          <div className="confirm-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className={`btn ${req.danger ? 'btn-danger' : 'btn-primary'}`}
                    disabled={needsInput && !text.trim()} data-testid="confirm-ok">
              {req.confirmLabel}
            </button>
          </div>
        </form>
      )}
    </dialog>
  )
}
