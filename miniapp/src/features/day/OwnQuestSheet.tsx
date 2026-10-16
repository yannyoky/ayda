import { useId, useState, type FormEvent } from 'react'
import { ApiError, type Schemas } from '../../api/client'
import { useAddOwnQuest } from '../../api/queries'
import { t } from '../../i18n'
import { haptic } from '../../telegram/webapp'
import { Sheet } from '../../ui/Sheet'
import { PrimaryButton } from '../../ui/states'

const categories: Schemas['Category'][] = ['project', 'sport', 'walk', 'home', 'learning', 'rest', 'social', 'city']
const durations = [15, 30, 45, 60, 90]

/** US-08: a quest the user words themselves; it is taken right away. */
export function OwnQuestSheet({ onClose, onAdded }: { onClose: () => void; onAdded?: () => void }) {
  const nameId = useId()
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState<Schemas['Category']>('project')
  const [duration, setDuration] = useState(30)
  const add = useAddOwnQuest()
  const limitReached = add.error instanceof ApiError && add.error.status === 409

  function submit(e: FormEvent) {
    e.preventDefault()
    add.mutate(
      { title: title.trim(), category, duration_min: duration },
      {
        onSuccess: () => {
          haptic('success')
          onClose()
          onAdded?.()
        },
      },
    )
  }

  return (
    <Sheet title={t.ownQuest.title} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <label htmlFor={nameId} className="text-sm font-bold">
            {t.ownQuest.name}
          </label>
          <input
            id={nameId}
            value={title}
            maxLength={120}
            required
            placeholder={t.ownQuest.namePlaceholder}
            onChange={(e) => setTitle(e.target.value)}
            className="h-12 rounded-field border-0 bg-surface px-4 text-[15px] font-semibold placeholder:text-muted"
          />
        </div>
        <Chips label={t.ownQuest.category} options={categories.map((c) => [c, t.quest.categories[c]])} value={category} onChange={setCategory} />
        <Chips label={t.ownQuest.duration} options={durations.map((d) => [d, t.quest.minutes(d)])} value={duration} onChange={setDuration} />
        {add.isError && (
          <p role="alert" className="m-0 text-sm font-bold">
            {limitReached ? t.ownQuest.limit : add.error.message}
          </p>
        )}
        <PrimaryButton type="submit" disabled={!title.trim() || add.isPending}>
          {t.ownQuest.add}
        </PrimaryButton>
      </form>
    </Sheet>
  )
}

function Chips<T extends string | number>({ label, options, value, onChange }: { label: string; options: [T, string][]; value: T; onChange: (v: T) => void }) {
  return (
    <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
      <legend className="mb-2 text-sm font-bold">{label}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map(([v, text]) => (
          <label
            key={String(v)}
            className="flex h-10 items-center rounded-field bg-surface px-3.5 text-sm font-bold has-[:checked]:bg-plate has-[:checked]:text-on-plate has-[:focus-visible]:outline-2"
          >
            <input type="radio" name={label} checked={value === v} onChange={() => onChange(v)} className="sr-only" />
            {text}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
