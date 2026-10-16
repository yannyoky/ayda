import { useId, useState, type FormEvent } from 'react'
import type { Schemas } from '../../api/client'
import { useSubmitCheckin } from '../../api/queries'
import { t } from '../../i18n'
import { haptic } from '../../telegram/webapp'
import { Icon } from '../../ui/Icon'

type Mood = Schemas['Mood']
const moods: Mood[] = ['energetic', 'normal', 'tired']
export const CHECKIN_MAX = 1000

/** Morning check-in on the dark plate (US-05). The text is private and never logged. */
export function CheckinCard({ checkin }: { checkin: Schemas['Checkin'] | null }) {
  const [editing, setEditing] = useState(checkin === null)
  if (!editing && checkin) {
    return (
      <section className="flex items-center gap-3 rounded-card bg-plate p-4 text-on-plate">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-tile bg-plate-2 text-accent">
          <Icon name="check" size={20} strokeWidth={2.6} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[15px] font-bold">{t.today.checkinDone(t.today.moods[checkin.mood].toLowerCase())}</span>
          {checkin.text && <span className="truncate text-xs font-semibold opacity-70">{checkin.text}</span>}
        </div>
        <button type="button" onClick={() => setEditing(true)} className="h-11 shrink-0 rounded-field bg-plate-2 px-4 text-sm font-extrabold text-on-plate">
          {t.today.checkinRedo}
        </button>
      </section>
    )
  }
  return <CheckinForm initial={checkin} onDone={() => setEditing(false)} />
}

function CheckinForm({ initial, onDone }: { initial: Schemas['Checkin'] | null; onDone: () => void }) {
  const textId = useId()
  const hintId = useId()
  const [text, setText] = useState(initial?.text ?? '')
  const [mood, setMood] = useState<Mood>(initial?.mood ?? 'normal')
  const submit = useSubmitCheckin()

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    haptic('tap')
    submit.mutate({ text: text.trim(), mood }, { onSuccess: onDone })
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3 rounded-card bg-plate p-4 text-on-plate">
      <label htmlFor={textId} className="font-display text-[17px] font-bold">
        {t.today.checkinTitle}
      </label>
      <textarea
        id={textId}
        aria-describedby={hintId}
        value={text}
        maxLength={CHECKIN_MAX}
        rows={3}
        placeholder={t.today.checkinPlaceholder}
        onChange={(e) => setText(e.target.value)}
        className="min-h-24 resize-none rounded-field border-0 bg-plate-2 p-3.5 text-[15px] leading-snug font-medium text-on-plate placeholder:text-on-plate/50"
      />
      <div role="radiogroup" aria-label={t.today.mood} className="grid grid-cols-3 gap-1.5 rounded-field bg-plate-2 p-1">
        {moods.map((m) => (
          <label
            key={m}
            className="flex h-10 items-center justify-center rounded-xl text-sm font-bold text-on-plate/70 has-[:checked]:bg-accent has-[:checked]:text-on-accent has-[:focus-visible]:outline-2"
          >
            <input type="radio" name="mood" value={m} checked={mood === m} onChange={() => setMood(m)} className="sr-only" />
            {t.today.moods[m]}
          </label>
        ))}
      </div>
      <div className="flex items-center justify-between gap-3">
        <span id={hintId} className="text-xs font-semibold opacity-60">
          {text.length > CHECKIN_MAX - 100 ? `${text.length}/${CHECKIN_MAX}` : `${t.today.checkinPrivate}. ${t.today.checkinHint}`}
        </span>
        <button
          type="submit"
          aria-label={t.today.checkinSubmit}
          disabled={submit.isPending}
          className="flex size-12 shrink-0 items-center justify-center rounded-field bg-accent text-on-accent disabled:opacity-60"
        >
          <Icon name="arrow" size={22} strokeWidth={2.4} />
        </button>
      </div>
      {submit.isError && (
        <p role="alert" className="m-0 text-sm font-bold">
          {submit.error.message}
        </p>
      )}
    </form>
  )
}
