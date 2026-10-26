import type { ReactNode } from 'react'
import { t } from '../i18n'

/** Full-screen centred message for launch states (loading, errors, outside Telegram). */
export function FullScreen({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col items-center justify-center gap-4 px-8 text-center">
      <div aria-hidden="true" className="flex size-16 items-center justify-center rounded-card bg-plate font-display text-2xl font-extrabold text-accent">
        A
      </div>
      <h1 className="m-0 font-display text-2xl font-bold">{title}</h1>
      {text && <p className="m-0 text-[15px] font-medium text-muted">{text}</p>}
      {action}
    </main>
  )
}

export function Splash() {
  return (
    <main aria-busy="true" className="flex min-h-dvh items-center justify-center">
      <div className="flex size-16 animate-pulse items-center justify-center rounded-card bg-plate font-display text-2xl font-extrabold text-accent">
        A
      </div>
      <span className="sr-only">{t.common.loading}</span>
    </main>
  )
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  type = 'button',
  className = '',
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  type?: 'button' | 'submit'
  className?: string
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`flex h-14 items-center justify-center gap-2.5 rounded-field bg-plate px-6 text-base font-extrabold text-on-plate disabled:opacity-50 ${className}`}
    >
      {children}
    </button>
  )
}

export function InlineError({ text, onRetry }: { text?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-card bg-surface p-4 text-[15px] font-semibold">
      <span>{text ?? t.common.errorGeneric}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="h-11 shrink-0 rounded-field bg-bg px-4 font-extrabold">
          {t.common.retry}
        </button>
      )}
    </div>
  )
}
