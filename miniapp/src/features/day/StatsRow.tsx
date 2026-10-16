import type { Schemas } from '../../api/client'
import { formatNumber, plural, t } from '../../i18n'

export function StatsRow({ day }: { day: Schemas['Day'] }) {
  const streak = day.streak.current_days
  return (
    <div className="grid grid-cols-2 gap-3">
      <section aria-label={t.today.streak} className="flex h-34 flex-col justify-between rounded-card bg-accent p-4 text-on-accent">
        <span className="text-[13px] font-bold">{t.today.streak}</span>
        <div className="flex items-baseline gap-1.5">
          <span className="font-display text-[52px] leading-none font-extrabold tracking-[-2px]">{streak}</span>
          <span className="text-sm font-bold">{plural(streak, t.today.days)}</span>
        </div>
      </section>
      <section aria-label={t.today.week} className="flex h-34 flex-col justify-between rounded-card bg-surface p-4">
        <span className="text-[13px] font-bold text-muted">{t.today.week}</span>
        <span className="font-display text-[34px] font-bold tracking-[-1px]">{formatNumber(day.points_week)}</span>
        <span className="w-fit rounded-[10px] bg-bg px-2 py-1 text-xs font-extrabold">{t.today.todayPoints(day.points_today)}</span>
      </section>
    </div>
  )
}
