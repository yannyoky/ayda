import { useId, useState, type FormEvent } from 'react'
import type { Schemas } from '../../api/client'
import { useAddHabit, useDeleteHabit, useMyHabits } from '../../api/queries'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'

type Direction = Schemas['HabitDirection']

export function HabitsEditor() {
  const habits = useMyHabits()
  return (
    <div className="flex flex-col gap-3">
      <HabitColumn direction="more" items={habits.data?.items ?? []} />
      <HabitColumn direction="less" items={habits.data?.items ?? []} />
    </div>
  )
}

function HabitColumn({ direction, items }: { direction: Direction; items: Schemas['Habit'][] }) {
  const id = useId()
  const [text, setText] = useState('')
  const add = useAddHabit()
  const remove = useDeleteHabit()
  const label = direction === 'more' ? t.onboarding.habits.more : t.onboarding.habits.less
  const placeholder = direction === 'more' ? t.onboarding.habits.morePlaceholder : t.onboarding.habits.lessPlaceholder

  function submit(e: FormEvent) {
    e.preventDefault()
    const value = text.trim()
    if (!value) return
    add.mutate({ direction, text: value }, { onSuccess: () => setText('') })
  }

  return (
    <section className="flex flex-col gap-2 rounded-card bg-surface p-4">
      <form onSubmit={submit} className="flex flex-col gap-2">
        <label htmlFor={id} className="font-display text-sm font-bold">
          {label}
        </label>
        <div className="flex gap-2">
          <input
            id={id}
            value={text}
            maxLength={100}
            placeholder={placeholder}
            onChange={(e) => setText(e.target.value)}
            className="h-12 min-w-0 flex-1 rounded-field border-0 bg-bg px-3 text-[15px] font-semibold placeholder:text-muted"
          />
          <button
            type="submit"
            aria-label={`${t.onboarding.habits.add}: ${label.toLowerCase()}`}
            disabled={!text.trim() || add.isPending}
            className="flex size-12 shrink-0 items-center justify-center rounded-field bg-accent text-on-accent disabled:opacity-40"
          >
            <Icon name="plus" size={20} strokeWidth={2.4} />
          </button>
        </div>
      </form>
      {items
        .filter((h) => h.direction === direction)
        .map((habit) => (
          <div key={habit.id} className="flex items-center justify-between gap-2 rounded-field bg-bg py-1 pr-1 pl-3">
            <span className="text-[15px] font-semibold">{habit.text}</span>
            <button
              type="button"
              aria-label={t.onboarding.habits.remove(habit.text)}
              onClick={() => remove.mutate(habit.id)}
              className="flex size-10 items-center justify-center rounded-tile text-muted"
            >
              <Icon name="close" size={18} />
            </button>
          </div>
        ))}
    </section>
  )
}
