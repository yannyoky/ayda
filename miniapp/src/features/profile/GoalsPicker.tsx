import { useGoalCatalog } from '../../api/queries'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'

export const MAX_GOALS = 5

export function GoalsPicker({ value, onChange }: { value: string[]; onChange: (codes: string[]) => void }) {
  const catalog = useGoalCatalog()
  const full = value.length >= MAX_GOALS
  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label={t.profile.goals} className="flex flex-wrap gap-2">
        {catalog.data?.items.map((goal) => {
          const on = value.includes(goal.code)
          return (
            <button
              key={goal.code}
              type="button"
              aria-pressed={on}
              disabled={!on && full}
              onClick={() => onChange(on ? value.filter((c) => c !== goal.code) : [...value, goal.code])}
              className={`flex h-11 items-center gap-1.5 rounded-field px-4 text-sm font-bold disabled:opacity-40 ${on ? 'bg-accent text-on-accent' : 'bg-surface text-ink'}`}
            >
              {on && <Icon name="check" size={16} strokeWidth={2.6} />}
              {goal.title}
            </button>
          )
        })}
      </div>
      {full && <p className="m-0 text-sm font-semibold text-muted">{t.onboarding.goals.limit}</p>}
    </div>
  )
}
