import type { ReactNode } from 'react'

export function ScreenHeader({ eyebrow, title, action }: { eyebrow?: string; title: string; action?: ReactNode }) {
  return (
    <header className="flex items-center justify-between gap-3 px-1">
      <div className="flex min-w-0 flex-col gap-0.5">
        {eyebrow && <span className="text-[13px] font-semibold text-muted">{eyebrow}</span>}
        <h1 className="m-0 font-display text-[26px] font-bold tracking-[-0.5px]">{title}</h1>
      </div>
      {action}
    </header>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-card bg-surface p-4 ${className}`}>{children}</section>
}
