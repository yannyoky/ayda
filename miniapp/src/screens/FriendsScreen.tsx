import { useState } from 'react'
import { useLadder, type LadderWeek } from '../api/queries'
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
  return (
    <>
      <ScreenHeader eyebrow={data ? t.friends.weekFrom(weekStart.format(new Date(data.week_start))) : undefined} title={t.friends.title} />
      <div role="radiogroup" aria-label={t.friends.title} className="flex gap-1.5 rounded-[20px] bg-surface p-1">
        {weeks.map((w) => (
          <label
            key={w}
            className="flex h-10 flex-1 items-center justify-center rounded-field text-sm font-bold text-muted has-[:checked]:bg-plate has-[:checked]:text-on-plate has-[:focus-visible]:outline-2"
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
