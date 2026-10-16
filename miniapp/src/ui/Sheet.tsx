import { useEffect, useId, useRef, type ReactNode } from 'react'
import { t } from '../i18n'
import { Icon } from './Icon'

/** Bottom sheet over a dimmed screen; Escape or a tap outside closes it. */
export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const titleId = useId()
  const panel = useRef<HTMLDivElement>(null)
  // Callers pass inline callbacks; keep the latest one without re-running the focus effect
  const close = useRef(onClose)
  useEffect(() => {
    close.current = onClose
  }, [onClose])

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    panel.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && close.current()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [])

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-[rgb(0_0_0/0.4)]" onClick={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90dvh] w-full max-w-[480px] flex-col gap-4 overflow-y-auto rounded-t-card bg-bg p-4 pb-[max(24px,env(safe-area-inset-bottom))] outline-none"
      >
        <div className="flex items-center justify-between gap-3">
          <h2 id={titleId} className="m-0 font-display text-lg font-bold">
            {title}
          </h2>
          <button type="button" aria-label={t.pick.close} onClick={onClose} className="flex size-11 items-center justify-center rounded-full bg-surface">
            <Icon name="close" size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
