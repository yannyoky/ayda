import { useState } from 'react'
import { useLadder, useToday, type LadderWeek } from '../api/queries'
import { StatsRow } from '../features/day/StatsRow'
import { FriendsList } from '../features/friends/FriendsList'
import { Ladder } from '../features/friends/Ladder'
import { t } from '../i18n'
import { ScreenHeader } from '../ui/primitives'
import { InlineError } from '../ui/states'

const weekStart = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' })
const weeks: LadderWeek[] = ['current', 'previous']

export function FriendsScreen() {
  const [week, setWeek] = useState<LadderWeek>('current')
  const ladder = useLadder(week)
  const data = ladder.data
  const today = useToday()
  return (
    <>
      <ScreenHeader eyebrow={data ? t.friends.weekFrom(weekStart.format(new Date(data.week_start))) : undefined} title={t.friends.title} />
      {today.data && <StatsRow day={today.data} />}
      <div role="radiogroup" aria-label={t.friends.title} className="relative flex gap-1.5 rounded-field bg-surface p-1">
        {/* One pill that slides between the options instead of jumping */}
        <span
          aria-hidden="true"
          className="absolute top-1 bottom-1 left-1 w-[calc(50%-7px)] rounded-segment bg-plate transition-transform duration-250 ease-out"
          style={{ transform: week === 'previous' ? 'translateX(calc(100% + 6px))' : 'none' }}
        />
        {weeks.map((w) => (
          <label
            key={w}
            className="relative flex h-10 flex-1 items-center justify-center rounded-segment text-sm font-bold text-muted transition-colors duration-250 has-[:checked]:text-on-plate has-[:focus-visible]:outline-2"
          >
            <input type="radio" name="week" checked={week === w} onChange={() => setWeek(w)} className="sr-only" />
            {t.friends.weeks[w]}
          </label>
        ))}
      </div>
      {ladder.isError && <InlineError onRetry={() => void ladder.refetch()} />}
      {data && data.entries.length > 1 && <Ladder entries={data.entries} />}
      {data && data.entries.length <= 1 && <p className="m-0 rounded-card bg-surface p-4 text-[15px] font-semibold text-muted">{t.friends.alone}</p>}
      <FriendsList />
    </>
  )
}
