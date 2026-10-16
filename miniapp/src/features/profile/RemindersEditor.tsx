import { useId } from 'react'
import type { Schemas } from '../../api/client'
import { t } from '../../i18n'

type Reminders = Schemas['Reminders']

const DEFAULTS = { morning_at: '08:30', evening_at: '20:30' } as const

export function RemindersEditor({ value, onChange }: { value: Reminders; onChange: (value: Reminders) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <ReminderRow label={t.onboarding.reminders.morning} time={value.morning_at} fallback={DEFAULTS.morning_at} onChange={(morning_at) => onChange({ ...value, morning_at })} />
      <ReminderRow label={t.onboarding.reminders.evening} time={value.evening_at} fallback={DEFAULTS.evening_at} onChange={(evening_at) => onChange({ ...value, evening_at })} />
    </div>
  )
}

function ReminderRow({
  label,
  time,
  fallback,
  onChange,
}: {
  label: string
  time: string | null
  fallback: string
  onChange: (time: string | null) => void
}) {
  const id = useId()
  const on = time !== null
  return (
    <div className="flex items-center gap-3 rounded-card bg-surface p-3 pl-4">
      <label htmlFor={`${id}-on`} className="flex-1 text-[15px] font-bold">
        {label}
      </label>
      {on ? (
        <input
          aria-label={`${label}: время`}
          type="time"
          value={time}
          required
          onChange={(e) => e.target.value && onChange(e.target.value)}
          className="h-11 rounded-field border-0 bg-bg px-3 font-display text-base font-bold"
        />
      ) : (
        <span className="text-sm font-semibold text-muted">{t.onboarding.reminders.off}</span>
      )}
      <input
        id={`${id}-on`}
        type="checkbox"
        role="switch"
        checked={on}
        onChange={(e) => onChange(e.target.checked ? fallback : null)}
        className="relative h-7 w-12 shrink-0 cursor-pointer appearance-none rounded-full bg-track transition-colors before:absolute before:top-1 before:left-1 before:size-5 before:rounded-full before:bg-surface before:transition-transform checked:bg-plate checked:before:translate-x-5"
      />
    </div>
  )
}
