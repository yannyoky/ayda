import { useState } from 'react'
import { useInterestCatalog } from '../../api/queries'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'

export const MAX_INTERESTS = 8
export const MAX_TAGS = 5
const MAX_TAG_LENGTH = 30

export interface InterestSelection {
  codes: string[]
  tags: string[]
}

export function InterestsPicker({ value, onChange }: { value: InterestSelection; onChange: (next: InterestSelection) => void }) {
  const catalog = useInterestCatalog()
  const [text, setText] = useState('')
  const full = value.codes.length >= MAX_INTERESTS
  const word = text.trim().toLowerCase()
  const canAdd = word.length > 0 && value.tags.length < MAX_TAGS && !value.tags.includes(word)

  function addTag(event: React.FormEvent) {
    event.preventDefault()
    if (!canAdd) return
    onChange({ ...value, tags: [...value.tags, word] })
    setText('')
  }

  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label={t.profile.interests} className="flex flex-wrap gap-2">
        {catalog.data?.items.map((interest) => {
          const on = value.codes.includes(interest.code)
          return (
            <button
              key={interest.code}
              type="button"
              aria-pressed={on}
              disabled={!on && full}
              onClick={() =>
                onChange({ ...value, codes: on ? value.codes.filter((c) => c !== interest.code) : [...value.codes, interest.code] })
              }
              className={`flex h-11 items-center gap-1.5 rounded-field px-4 text-sm font-bold disabled:opacity-40 ${on ? 'bg-accent text-on-accent' : 'bg-surface text-ink'}`}
            >
              {on && <Icon name="check" size={16} strokeWidth={2.6} />}
              {interest.title}
            </button>
          )
        })}
      </div>
      {full && <p className="m-0 text-sm font-semibold text-muted">{t.onboarding.interests.limit}</p>}
      <form onSubmit={addTag} className="flex flex-col gap-2">
        <label htmlFor="interest-tag" className="font-display text-sm font-bold">
          {t.onboarding.interests.own}
        </label>
        <div className="flex gap-2">
          <input
            id="interest-tag"
            value={text}
            maxLength={MAX_TAG_LENGTH}
            placeholder={t.onboarding.interests.ownPlaceholder}
            onChange={(e) => setText(e.target.value)}
            className="h-12 min-w-0 flex-1 rounded-field border-0 bg-bg px-3 text-[15px] font-semibold placeholder:text-muted"
          />
          <button
            type="submit"
            aria-label={t.onboarding.interests.add}
            disabled={!canAdd}
            className="flex size-12 shrink-0 items-center justify-center rounded-field bg-accent text-on-accent disabled:opacity-40"
          >
            <Icon name="plus" size={20} strokeWidth={2.4} />
          </button>
        </div>
      </form>
      <div className="flex flex-wrap gap-2">
        {value.tags.map((tag) => (
          <span key={tag} className="flex h-10 items-center gap-1 rounded-field bg-bg py-1 pr-1 pl-3 text-[15px] font-semibold">
            {tag}
            <button
              type="button"
              aria-label={t.onboarding.interests.remove(tag)}
              onClick={() => onChange({ ...value, tags: value.tags.filter((x) => x !== tag) })}
              className="flex size-8 items-center justify-center rounded-tile text-muted"
            >
              <Icon name="close" size={16} />
            </button>
          </span>
        ))}
      </div>
    </div>
  )
}
