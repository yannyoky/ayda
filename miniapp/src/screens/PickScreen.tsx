import { useCallback, useState } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { ApiError, type Schemas } from '../api/client'
import { useReplaceQuest, useTakeQuests, useToday } from '../api/queries'
import { eventSummary } from '../features/day/event'
import { EventLink } from '../features/day/EventLink'
import { OwnQuestSheet } from '../features/day/OwnQuestSheet'
import { t } from '../i18n'
import { useBackButton } from '../telegram/useBackButton'
import { haptic } from '../telegram/webapp'
import { Icon } from '../ui/Icon'
import { Sheet } from '../ui/Sheet'
import { Splash } from '../ui/states'

/** Quest picker (US-07): take any number (points for the first few completed), swap what does not fit. */
export function PickScreen() {
  const navigate = useNavigate()
  const today = useToday()
  const take = useTakeQuests()
  const replace = useReplaceQuest()
  const [selected, setSelected] = useState<string[]>([])
  const [replacing, setReplacing] = useState<Schemas['DayQuest'] | null>(null)
  const [ownOpen, setOwnOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const back = useCallback(() => navigate('/'), [navigate])
  useBackButton(back)

  const day = today.data
  if (!day) return <Splash />
  if (day.pool_status === 'none') return <Navigate to="/" replace />

  const offered = day.quests.filter((q) => q.state === 'offered')
  const left = day.limits.max_taken - day.limits.taken
  const chosen = selected.filter((id) => offered.some((q) => q.id === id))
  const points = offered.filter((q) => chosen.includes(q.id)).reduce((sum, q) => sum + q.base_points, 0)

  function toggle(id: string) {
    haptic('tap')
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : cur.length < left ? [...cur, id] : cur))
  }

  function doReplace(quest: Schemas['DayQuest'], reason?: Schemas['RejectReason']) {
    setReplacing(null)
    setSelected((cur) => cur.filter((id) => id !== quest.id))
    replace.mutate(
      { id: quest.id, reason },
      {
        onSuccess: (r) => setNotice(r.replacement ? t.pick.replacementsLeft(r.replacements_left) : t.pick.noAlternative),
        onError: (e) => setNotice(e instanceof ApiError && e.status === 409 ? t.pick.noReplacements : e.message),
      },
    )
  }

  function takeSelected() {
    take.mutate(chosen, {
      onSuccess: () => {
        haptic('success')
        navigate('/')
      },
      onError: (e) => setNotice(e.message),
    })
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-3 px-4 pt-[max(20px,env(safe-area-inset-top))] pb-32">
      <header className="flex items-start justify-between gap-3 px-1">
        <div className="flex flex-col gap-1">
          <h1 className="m-0 font-display text-2xl font-bold tracking-[-0.5px]">{t.pick.title}</h1>
          <span className="text-[13px] font-semibold text-muted">{t.pick.subtitle(left, day.limits.max_scored)}</span>
        </div>
        <button type="button" aria-label={t.pick.close} onClick={back} className="flex size-11 shrink-0 items-center justify-center rounded-full bg-surface">
          <Icon name="close" size={20} strokeWidth={2.2} />
        </button>
      </header>

      {notice && (
        <p role="status" className="m-0 rounded-field bg-plate px-4 py-3 text-sm font-bold text-on-plate">
          {notice}
        </p>
      )}

      {day.pool_status === 'generating' && offered.length === 0 ? (
        <p role="status" className="m-0 flex items-center gap-3 rounded-card bg-surface p-4 text-[15px] font-semibold text-muted">
          <span aria-hidden="true" className="size-3 animate-pulse rounded-full bg-accent" />
          {t.today.generating}
        </p>
      ) : offered.length === 0 ? (
        <p className="m-0 rounded-card bg-surface p-4 text-[15px] font-semibold text-muted">{t.pick.empty}</p>
      ) : (
        <ul className="m-0 grid list-none grid-cols-2 gap-2.5 p-0">
          {offered.map((quest) => (
            <QuestCard
              key={quest.id}
              quest={quest}
              selected={chosen.includes(quest.id)}
              disabled={left === 0}
              canReplace={day.limits.replacements_left > 0 && !replace.isPending}
              onToggle={() => toggle(quest.id)}
              onReplace={() => setReplacing(quest)}
            />
          ))}
        </ul>
      )}

      <div className="fixed inset-x-0 bottom-0 z-10 mx-auto flex max-w-[480px] gap-2 bg-bg px-4 pt-3 pb-[max(24px,env(safe-area-inset-bottom))]">
        <button
          type="button"
          onClick={() => setOwnOpen(true)}
          disabled={left === 0}
          className="flex h-14 items-center gap-2 rounded-[20px] bg-surface px-4.5 text-sm font-extrabold disabled:opacity-50"
        >
          <Icon name="plus" size={18} strokeWidth={2.2} />
          {t.today.own}
        </button>
        <button
          type="button"
          disabled={chosen.length === 0 || take.isPending}
          onClick={takeSelected}
          className="flex h-14 flex-1 items-center justify-center gap-2.5 rounded-[20px] bg-plate text-base font-extrabold text-on-plate disabled:opacity-50"
        >
          {t.pick.take(chosen.length)}
          {points > 0 && <span className="rounded-[10px] bg-accent px-2 py-1 text-[13px] text-on-accent">+{points}</span>}
        </button>
      </div>

      {replacing && (
        <Sheet title={t.pick.reasonTitle} onClose={() => setReplacing(null)}>
          <p className="m-0 text-[15px] font-semibold text-muted">{replacing.title}</p>
          <div className="grid grid-cols-2 gap-2">
            {(['no_time', 'dont_want', 'cant'] as const).map((r) => (
              <button key={r} type="button" onClick={() => doReplace(replacing, r)} className="h-12 rounded-field bg-surface text-sm font-extrabold">
                {t.pick.reasons[r]}
              </button>
            ))}
            <button type="button" onClick={() => doReplace(replacing)} className="h-12 rounded-field bg-plate text-sm font-extrabold text-on-plate">
              {t.pick.noReason}
            </button>
          </div>
          <span className="text-xs font-semibold text-muted">{t.pick.replacementsLeft(day.limits.replacements_left)}</span>
        </Sheet>
      )}
      {ownOpen && <OwnQuestSheet onClose={() => setOwnOpen(false)} onAdded={back} />}
    </main>
  )
}

function QuestCard({
  quest,
  selected,
  disabled,
  canReplace,
  onToggle,
  onReplace,
}: {
  quest: Schemas['DayQuest']
  selected: boolean
  disabled: boolean
  canReplace: boolean
  onToggle: () => void
  onReplace: () => void
}) {
  return (
    <li className={`relative flex min-h-40 flex-col rounded-3xl ${selected ? 'bg-accent text-on-accent' : 'bg-surface text-ink'}`}>
      <button
        type="button"
        aria-pressed={selected}
        disabled={disabled && !selected}
        onClick={onToggle}
        className="flex flex-1 flex-col justify-between gap-2 rounded-3xl p-3.5 text-left disabled:opacity-60"
      >
        <span className="flex w-full items-center justify-between">
          <span className={`rounded-lg px-2 py-1 text-[11px] font-extrabold uppercase ${selected ? 'bg-surface text-ink' : 'bg-bg'}`}>
            {t.quest.categories[quest.category]}
          </span>
          {selected ? (
            <span className="flex size-7 items-center justify-center rounded-full bg-plate text-on-plate">
              <Icon name="check" size={16} strokeWidth={3} />
            </span>
          ) : (
            <span className="size-7 rounded-full border-2 border-track" />
          )}
        </span>
        <span className="text-base leading-tight font-extrabold">{quest.title}</span>
        {quest.why && <span className={`text-xs leading-snug font-semibold ${selected ? '' : 'text-muted'}`}>{quest.why}</span>}
        {quest.event && <span className="text-xs leading-snug font-bold">{eventSummary(quest.event)}</span>}
        <span className={`text-xs font-bold ${selected ? '' : 'text-muted'}`}>
          {t.quest.minutes(quest.duration_min)} · {t.quest.points(quest.base_points)}
        </span>
      </button>
      {quest.event && <EventLink event={quest.event} title={quest.title} variant="card" />}
      {canReplace && (
        <button
          type="button"
          aria-label={t.pick.notTodayFor(quest.title)}
          onClick={onReplace}
          className="mx-2 mb-2 flex h-9 items-center justify-center gap-1.5 rounded-xl bg-[rgb(0_0_0/0.06)] text-xs font-extrabold"
        >
          <Icon name="refresh" size={14} strokeWidth={2.4} />
          {t.pick.notToday}
        </button>
      )}
    </li>
  )
}
