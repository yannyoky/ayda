import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import type { Schemas } from '../../api/client'
import { formatNumber, plural, t } from '../../i18n'
import { Icon } from '../../ui/Icon'

const SEEN_KEY = 'ayda.streak.seen'

/** The streak the user saw last time; storage can be missing (private mode, tests). */
function lastSeen(): number | null {
  try {
    const raw = window.localStorage.getItem(SEEN_KEY)
    return raw === null ? null : Number(raw)
  } catch {
    return null
  }
}

function remember(streak: number): void {
  try {
    window.localStorage.setItem(SEEN_KEY, String(streak))
  } catch {
    // Not critical: the number just won't roll next time
  }
}

/** Big numbers shrink so "1000 дней" still fits the half-width tile. */
function streakSize(streak: number): string {
  const digits = String(streak).length
  if (digits >= 4) return 'text-[36px] tracking-[-1.5px]'
  if (digits === 3) return 'text-[44px] tracking-[-2px]'
  return 'text-[52px] tracking-[-2px]'
}

export function StatsRow({ day }: { day: Schemas['Day'] }) {
  const streak = day.streak.current_days
  // The number rolls up once, the first time the user sees a longer streak
  const [grew] = useState(() => {
    const seen = lastSeen()
    return seen !== null && streak > seen
  })
  useEffect(() => remember(streak), [streak])

  return (
    <div className="grid grid-cols-2 gap-3">
      {streak === 0 ? (
        <section aria-label={t.today.streak} className="flex h-34 flex-col justify-between rounded-card bg-plate p-4 text-on-plate">
          <span className="text-[13px] font-bold opacity-70">{t.today.streak}</span>
          <span className="font-display text-base leading-tight font-bold">{t.today.streakStart}</span>
          <Link to="/" className="press flex w-fit items-center gap-1.5 rounded-chip bg-accent px-2.5 py-1.5 text-xs font-extrabold text-on-accent no-underline">
            {t.today.streakStartCta}
            <Icon name="arrow" size={14} strokeWidth={2.6} />
          </Link>
        </section>
      ) : (
        <section aria-label={t.today.streak} className="flex h-34 min-w-0 flex-col justify-between rounded-card bg-accent p-4 text-on-accent">
          <span className="text-[13px] font-bold">{t.today.streak}</span>
          <div className="flex flex-wrap items-baseline gap-x-1.5 overflow-hidden">
            <span key={grew ? 'grew' : 'same'} className={`font-display leading-none font-extrabold tabular-nums ${streakSize(streak)} ${grew ? 'animate-roll-in' : ''}`}>
              {streak}
            </span>
            <span className="text-sm font-bold">{plural(streak, t.today.days)}</span>
          </div>
        </section>
      )}
      <section aria-label={t.today.week} className="flex h-34 min-w-0 flex-col justify-between rounded-card bg-surface p-4">
        <span className="text-[13px] font-bold text-muted">{t.today.week}</span>
        <span className="truncate font-display text-[34px] font-bold tracking-[-1px] tabular-nums">{formatNumber(day.points_week)}</span>
        <span className="w-fit rounded-chip bg-bg px-2 py-1 text-xs font-extrabold">{t.today.todayPoints(day.points_today)}</span>
      </section>
    </div>
  )
}
