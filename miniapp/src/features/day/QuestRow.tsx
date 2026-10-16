import type { Schemas } from '../../api/client'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'
import { CategoryIcon } from '../../ui/quest'

/** A taken, completed or expired quest on the Today card. */
export function QuestRow({ quest, onDone }: { quest: Schemas['DayQuest']; onDone?: () => void }) {
  const completed = quest.state === 'completed'
  const expired = quest.state === 'expired'
  const meta = completed
    ? `${t.today.completed} · ${quest.visibility ? t.today.visibilityDone[quest.visibility] : ''}`
    : expired
      ? t.today.expired
      : [t.quest.minutes(quest.duration_min), quest.why].filter(Boolean).join(' · ')
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
        <span className="truncate text-xs font-semibold text-muted">{meta}</span>
      </div>
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
