import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { Schemas } from '../api/client'
import { useMe, useToday } from '../api/queries'
import { CoopInvites } from '../features/coop/CoopInvites'
import { CoopSheet } from '../features/coop/CoopSheet'
import { CheckinCard } from '../features/day/CheckinCard'
import { OwnQuestSheet } from '../features/day/OwnQuestSheet'
import { QuestRow } from '../features/day/QuestRow'
import { TopEventsCard } from '../features/events/TopEventsCard'
import { formatShortDay, t } from '../i18n'
import { Icon } from '../ui/Icon'
import { ScreenHeader } from '../ui/primitives'
import { InlineError } from '../ui/states'

type Stage = 'checkin' | 'pick' | 'doing' | 'done'

/** Where the day is: the header title follows it, so the screen always says what is next. */
function dayStage(day: Schemas['Day']): Stage {
  const mine = day.quests.filter((q) => q.state !== 'offered')
  if (!day.checkin && mine.length === 0) return 'checkin'
  if (mine.length === 0) return 'pick'
  if (mine.some((q) => q.state === 'taken')) return 'doing'
  return 'done'
}

export function TodayScreen() {
  const me = useMe().data as Schemas['Me']
  const today = useToday()
  const day = today.data
  // The date, city and weather are one quiet line; the title is the next step of the day.
  // Streak and points live on the friends tab, so this screen keeps its room for the day itself.
  const weather = day?.weather
  const eyebrow = [formatShortDay(new Date()), me.city?.name, weather && t.today.weather(weather.temperature_c, t.today.conditions[weather.condition])]
    .filter(Boolean)
    .join(' · ')
  const stage = day ? dayStage(day) : null
  const mine = day ? day.quests.filter((q) => q.state !== 'offered') : []
  const completed = mine.filter((q) => q.state === 'completed').length
  const title = stage ? (stage === 'doing' ? t.today.stage.doing(completed, mine.length) : t.today.stage[stage]) : t.nav.today
  return (
    <>
      <ScreenHeader eyebrow={eyebrow} title={title} />
      {today.isError && <InlineError onRetry={() => void today.refetch()} />}
      {day && (
        <>
          {/* One card for the day: the check-in plate on top, the quests tucked under it */}
          <div className="flex flex-col">
            <CheckinCard key={day.checkin?.submitted_at ?? 'none'} checkin={day.checkin} />
            {stage !== 'checkin' && <QuestsCard day={day} />}
          </div>
          <CoopInvites />
          <TopEventsCard />
        </>
      )}
    </>
  )
}

function QuestsCard({ day }: { day: Schemas['Day'] }) {
  const navigate = useNavigate()
  const [ownOpen, setOwnOpen] = useState(false)
  const [coopFor, setCoopFor] = useState<Schemas['DayQuest'] | null>(null)
  const mine = day.quests.filter((q) => q.state !== 'offered')
  const offered = day.quests.filter((q) => q.state === 'offered').length
  const left = day.limits.max_taken - day.limits.taken

  return (
    <section aria-labelledby="quests-title" className="-mt-7 flex flex-col rounded-b-card bg-surface px-4 pt-11 pb-4">
      <div className="flex items-center justify-between pb-1.5">
        <h2 id="quests-title" className="m-0 font-display text-base font-bold">
          {t.today.questsTitle}
        </h2>
        <span className="text-[13px] font-bold text-muted">{t.today.scoredOf(day.limits.scored, day.limits.max_scored)}</span>
      </div>
      {mine.length > 0 && <Progress quests={mine} />}

      {day.pool_status === 'generating' && (
        <p role="status" className="m-0 flex items-center gap-3 py-3 text-[15px] font-semibold text-muted">
          <span aria-hidden="true" className="size-3 animate-pulse rounded-full bg-accent" />
          {t.today.generating}
        </p>
      )}
      {day.pool_status === 'failed' && <p className="m-0 py-2 text-sm font-semibold text-muted">{t.today.poolFailed}</p>}

      {mine.length > 0 ? (
        <ul className="m-0 list-none p-0">
          {mine.map((q) => (
            <QuestRow
              key={q.id}
              quest={q}
              onDone={() => navigate(`/quest/${q.id}/done`)}
              onInvite={q.source === 'coop' ? undefined : () => setCoopFor(q)}
            />
          ))}
        </ul>
      ) : (
        day.pool_status !== 'generating' && day.pool_status !== 'none' && <p className="m-0 py-2 text-sm font-semibold text-muted">{t.today.noneTaken}</p>
      )}

      {left > 0 && (
        <div className="flex gap-2 pt-3">
          {offered > 0 && (
            <Link
              to="/pick"
              className="flex h-12 flex-1 items-center justify-center gap-2 rounded-field bg-plate text-[15px] font-extrabold text-on-plate no-underline"
            >
              {mine.length > 0 ? t.today.pickMore : t.today.pickCta}
              <Icon name="arrow" size={18} strokeWidth={2.4} />
            </Link>
          )}
          <button
            type="button"
            onClick={() => setOwnOpen(true)}
            className={`flex h-12 items-center justify-center gap-1.5 rounded-field bg-bg px-4 text-sm font-extrabold ${offered > 0 ? '' : 'flex-1'}`}
          >
            <Icon name="plus" size={18} strokeWidth={2.4} />
            {t.today.own}
          </button>
        </div>
      )}
      {ownOpen && <OwnQuestSheet onClose={() => setOwnOpen(false)} />}
      {coopFor && <CoopSheet quest={coopFor} onClose={() => setCoopFor(null)} />}
    </section>
  )
}

/** One segment per quest taken today, filled as they are done. */
function Progress({ quests }: { quests: Schemas['DayQuest'][] }) {
  const done = quests.filter((q) => q.state === 'completed').length
  return (
    <div role="progressbar" aria-label={t.today.progress} aria-valuemin={0} aria-valuemax={quests.length} aria-valuenow={done} className="flex gap-1 pb-1.5">
      {quests.map((q) => (
        <span key={q.id} className="h-1.5 flex-1 overflow-hidden rounded-full bg-track">
          <span
            className="block h-full origin-left rounded-full bg-accent transition-transform duration-500 ease-out"
            style={{ transform: q.state === 'completed' ? 'none' : 'scaleX(0)' }}
          />
        </span>
      ))}
    </div>
  )
}
