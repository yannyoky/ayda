import { Link } from 'react-router'
import type { Schemas } from '../../api/client'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'
import { CategoryIcon } from '../../ui/quest'
import { eventSummary } from './event'
import { EventLink } from './EventLink'

/** A taken, completed or expired quest on the Today card; `onInvite` offers to do it with
 * friends (US-18), a co-op quest links to its co-op, and an event quest shows its time,
 * place and price with a link to the source (US-19). */
export function QuestRow({ quest, onDone, onInvite }: { quest: Schemas['DayQuest']; onDone?: () => void; onInvite?: () => void }) {
  const completed = quest.state === 'completed'
  const expired = quest.state === 'expired'
  const meta = completed
    ? `${t.today.completed} · ${quest.visibility ? t.today.visibilityDone[quest.visibility] : ''}`
    : expired
      ? t.today.expired
      : quest.event
        ? eventSummary(quest.event)
        : [quest.coop_id ? t.coop.together : null, t.quest.minutes(quest.duration_min), quest.why].filter(Boolean).join(' · ')
  return (
    <li className="flex items-center gap-3 border-t border-bg py-2.5 first:border-t-0">
      {completed ? (
        <span className="flex size-11 shrink-0 items-center justify-center rounded-tile bg-plate text-on-plate">
          <Icon name="check" size={20} strokeWidth={2.4} />
        </span>
      ) : (
        <CategoryIcon category={quest.category} />
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className={`text-[15px] font-bold ${completed || expired ? 'text-muted line-through' : ''}`}>{quest.title}</span>
        <span className={`text-xs font-semibold text-muted ${quest.event ? '' : 'truncate'}`}>{meta}</span>
        {quest.event && !completed && !expired && <EventLink event={quest.event} title={quest.title} variant="inline" />}
      </div>
      {quest.coop_id ? (
        <Link
          to={`/coops/${quest.coop_id}`}
          aria-label={t.coop.open(quest.title)}
          className="flex size-10 shrink-0 items-center justify-center rounded-field bg-bg text-ink"
        >
          <Icon name="friends" size={18} strokeWidth={2.2} />
        </Link>
      ) : (
        quest.state === 'taken' &&
        onInvite && (
          <button
            type="button"
            onClick={onInvite}
            aria-label={t.coop.inviteTo(quest.title)}
            className="flex size-10 shrink-0 items-center justify-center rounded-field bg-bg"
          >
            <Icon name="friends" size={18} strokeWidth={2.2} />
          </button>
        )
      )}
      {quest.state === 'taken' && onDone ? (
        <button
          type="button"
          onClick={onDone}
          aria-label={`${t.today.done}: ${quest.title}`}
          className="h-10 shrink-0 rounded-field bg-accent px-3.5 text-sm font-extrabold text-on-accent"
        >
          {t.today.done}
        </button>
      ) : (
        <span className="shrink-0 text-sm font-extrabold">{t.quest.points(quest.points_awarded ?? quest.base_points)}</span>
      )}
    </li>
  )
}
