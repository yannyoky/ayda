import { useState } from 'react'
import { Link } from 'react-router'
import type { Schemas } from '../../api/client'
import { t } from '../../i18n'
import { haptic } from '../../telegram/webapp'
import { Icon, type IconName } from '../../ui/Icon'
import { CategoryIcon } from '../../ui/quest'
import { Sheet } from '../../ui/Sheet'
import { eventSummary } from './event'
import { EventLink } from './EventLink'

/** A taken, completed or expired quest on the Today card. The row keeps only "Готово" so the
 * title has room; a tap on the title opens a sheet with the rest: discuss it with the assistant,
 * do it with friends (US-18) or open its co-op, and the event link (US-19). */
export function QuestRow({ quest, onDone, onInvite }: { quest: Schemas['DayQuest']; onDone?: () => void; onInvite?: () => void }) {
  const [open, setOpen] = useState(false)
  const taken = quest.state === 'taken'
  const completed = quest.state === 'completed'
  const expired = quest.state === 'expired'
  const meta = questMeta(quest)
  const done = () => {
    haptic('tap')
    onDone?.()
  }
  return (
    <li className="flex items-center gap-3 border-t border-bg py-2.5 first:border-t-0">
      {completed ? (
        <span className="flex size-11 shrink-0 items-center justify-center rounded-tile bg-plate text-on-plate">
          <Icon name="check" size={20} strokeWidth={2.4} />
        </span>
      ) : (
        <CategoryIcon category={quest.category} />
      )}
      <button
        type="button"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
        disabled={!taken}
        className="flex min-w-0 flex-1 flex-col items-start gap-0.5 text-left disabled:cursor-default disabled:active:transform-none"
      >
        <span className={`text-[15px] leading-snug font-bold [overflow-wrap:anywhere] ${completed || expired ? 'text-muted line-through' : ''}`}>{quest.title}</span>
        <span className="line-clamp-1 text-xs font-semibold text-muted">{meta}</span>
      </button>
      {taken && onDone ? (
        <button
          type="button"
          onClick={done}
          aria-label={`${t.today.done}: ${quest.title}`}
          className="h-10 shrink-0 rounded-field bg-accent px-3.5 text-sm font-extrabold text-on-accent"
        >
          {t.today.done}
        </button>
      ) : (
        <span className="shrink-0 text-sm font-extrabold">{t.quest.points(quest.points_awarded ?? quest.base_points)}</span>
      )}
      {open && (
        <QuestActions
          quest={quest}
          onClose={() => setOpen(false)}
          onDone={onDone ? done : undefined}
          onInvite={
            onInvite
              ? () => {
                  setOpen(false)
                  onInvite()
                }
              : undefined
          }
        />
      )}
    </li>
  )
}

function questMeta(quest: Schemas['DayQuest']): string {
  if (quest.state === 'completed') return `${t.today.completed} · ${quest.visibility ? t.today.visibilityDone[quest.visibility] : ''}`
  if (quest.state === 'expired') return t.today.expired
  if (quest.event) return eventSummary(quest.event)
  return [quest.coop_id ? t.coop.together : null, t.quest.minutes(quest.duration_min), quest.why].filter(Boolean).join(' · ')
}

const action = 'press flex h-14 w-full items-center gap-3 rounded-field bg-surface px-4 text-left text-[15px] font-extrabold text-ink no-underline'

function ActionIcon({ name }: { name: IconName }) {
  return (
    <span className="flex size-9 shrink-0 items-center justify-center rounded-tile bg-bg">
      <Icon name={name} size={18} strokeWidth={2.2} />
    </span>
  )
}

function QuestActions({
  quest,
  onClose,
  onDone,
  onInvite,
}: {
  quest: Schemas['DayQuest']
  onClose: () => void
  onDone?: () => void
  onInvite?: () => void
}) {
  return (
    <Sheet title={quest.title} onClose={onClose}>
      <p className="m-0 text-sm font-semibold text-muted">{questMeta(quest)}</p>
      {quest.event && <EventLink event={quest.event} title={quest.title} variant="sheet" />}
      <div className="flex flex-col gap-2">
        <Link to={`/assistant?quest=${quest.id}`} aria-label={t.assistant.discussQuest(quest.title)} className={action}>
          <ActionIcon name="spark" />
          {t.today.actions.discuss}
        </Link>
        {quest.coop_id ? (
          <Link to={`/coops/${quest.coop_id}`} aria-label={t.coop.open(quest.title)} className={action}>
            <ActionIcon name="friends" />
            {t.today.actions.coop}
          </Link>
        ) : (
          onInvite && (
            <button type="button" onClick={onInvite} aria-label={t.coop.inviteTo(quest.title)} className={action}>
              <ActionIcon name="friends" />
              {t.today.actions.invite}
            </button>
          )
        )}
      </div>
      {onDone && (
        <button type="button" onClick={onDone} className="h-14 rounded-field bg-accent text-base font-extrabold text-on-accent">
          {t.today.actions.done}
        </button>
      )}
    </Sheet>
  )
}
