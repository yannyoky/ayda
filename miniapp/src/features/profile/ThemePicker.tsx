import type { Theme } from '../../app/theme'
import { t } from '../../i18n'

const themes: Theme[] = ['graphite', 'plum']

export function ThemePicker({ value, onChange }: { value: Theme; onChange: (theme: Theme) => void }) {
  return (
    <div role="radiogroup" aria-label={t.profile.theme} className="grid grid-cols-2 gap-2">
      {themes.map((name) => (
        <label
          key={name}
          data-theme={name}
          className="flex flex-col gap-3 rounded-card bg-bg p-3 font-bold outline-offset-2 has-[:checked]:outline-2 has-[:checked]:outline-ink has-[:focus-visible]:outline-2"
        >
          <input type="radio" name="theme" value={name} checked={value === name} onChange={() => onChange(name)} className="sr-only" />
          <span aria-hidden="true" className="flex h-16 gap-1.5">
            <span className="flex-1 rounded-tile bg-plate" />
            <span className="flex-1 rounded-tile bg-accent" />
            <span className="flex-1 rounded-tile bg-surface" />
          </span>
          {t.profile.themes[name]}
        </label>
      ))}
    </div>
  )
}
