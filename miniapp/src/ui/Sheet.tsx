import { useEffect, useId, useRef, useState, type PointerEvent, type ReactNode } from 'react'
import { haptic } from '../telegram/webapp'
import { t } from '../i18n'
import { Icon } from './Icon'

/** Exit is quicker than entry: the user already decided, the system just responds. */
const EXIT_MS = 200
/** A flick faster than this (px/ms) closes the sheet whatever the distance. */
const FLICK_SPEED = 0.11

function animated(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Bottom sheet over a dimmed screen. It slides up on open; Escape, a tap outside, the close
 * button or a swipe down on its top area slides it away.
 */
export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const titleId = useId()
  const panel = useRef<HTMLDivElement>(null)
  const [closing, setClosing] = useState(false)
  const drag = useRef<{ y: number; at: number; dy: number } | null>(null)
  // Callers pass inline callbacks; keep the latest one without re-running the focus effect
  const close = useRef(onClose)
  useEffect(() => {
    close.current = onClose
  }, [onClose])

  const closingRef = useRef(false)
  const dismiss = () => {
    if (closingRef.current) return
    if (!animated()) {
      close.current()
      return
    }
    closingRef.current = true
    setClosing(true)
    window.setTimeout(() => close.current(), EXIT_MS)
  }
  const dismissRef = useRef(dismiss)
  useEffect(() => {
    dismissRef.current = dismiss
  })

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    panel.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && dismissRef.current()
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [])

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    if (!e.isPrimary || (e.target as HTMLElement).closest('button')) return
    drag.current = { y: e.clientY, at: e.timeStamp, dy: 0 }
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current
    const el = panel.current
    if (!d || !el) return
    const raw = e.clientY - d.y
    // Dragging up meets rising resistance instead of a hard stop
    d.dy = raw > 0 ? raw : -Math.sqrt(-raw) * 2
    el.style.transition = 'none'
    el.style.transform = `translateY(${d.dy}px)`
  }

  function onPointerUp(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current
    const el = panel.current
    drag.current = null
    if (!d || !el) return
    el.style.transition = ''
    const speed = d.dy / Math.max(1, e.timeStamp - d.at)
    if (d.dy > el.offsetHeight * 0.3 || (d.dy > 10 && speed > FLICK_SPEED)) {
      haptic('tap')
      el.style.transform = ''
      dismiss()
    } else {
      el.style.transform = ''
    }
  }

  return (
    <div
      className={`sheet-backdrop fixed inset-0 z-40 flex items-end justify-center bg-[rgb(0_0_0/0.4)] ${closing ? 'opacity-0' : ''}`}
      style={closing ? { transition: `opacity ${EXIT_MS}ms ease-out` } : undefined}
      onClick={() => dismiss()}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={`sheet-panel flex max-h-[90dvh] w-full max-w-[480px] flex-col overflow-y-auto rounded-t-card bg-bg px-4 pb-[max(24px,env(safe-area-inset-bottom))] outline-none`}
        style={closing ? { transform: 'translateY(100%)', transition: `transform ${EXIT_MS}ms var(--ease-out)` } : undefined}
      >
        <div
          className="sticky top-0 z-10 -mx-4 flex touch-none flex-col gap-2 bg-bg px-4 pt-2 pb-4"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <span aria-hidden="true" className="mx-auto h-1 w-9 rounded-full bg-track" />
          <div className="flex items-center justify-between gap-3">
            <h2 id={titleId} className="m-0 font-display text-lg font-bold">
              {title}
            </h2>
            <button
              type="button"
              aria-label={t.pick.close}
              onClick={() => dismiss()}
              className="flex size-11 shrink-0 items-center justify-center rounded-full bg-surface"
            >
              <Icon name="close" size={20} />
            </button>
          </div>
        </div>
        <div className="flex flex-col gap-4">{children}</div>
      </div>
    </div>
  )
}
