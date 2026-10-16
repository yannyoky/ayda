import { useTheme, type Theme } from '../app/theme'
import { t } from '../i18n'
import { Card, ScreenHeader } from '../ui/primitives'

const themes: Theme[] = ['graphite', 'plum']

export function ProfileScreen() {
  const { theme, setTheme } = useTheme()
  return (
    <>
      <ScreenHeader title={t.profile.title} />
      <Card>
        <fieldset className="m-0 flex flex-col gap-3 border-0 p-0">
          <legend className="mb-3 font-display text-base font-bold">{t.profile.theme}</legend>
          <div className="grid grid-cols-2 gap-2">
            {themes.map((name) => (
              <label
                key={name}
                data-theme={name}
                className="flex h-14 items-center gap-3 rounded-field bg-bg px-3 font-bold has-[:checked]:outline-2 has-[:checked]:outline-ink"
              >
                <input
                  type="radio"
                  name="theme"
                  value={name}
                  checked={theme === name}
                  onChange={() => setTheme(name)}
                  className="sr-only"
                />
                <span aria-hidden="true" className="size-6 rounded-full border-4 border-plate bg-accent" />
                {t.profile.themes[name]}
              </label>
            ))}
          </div>
        </fieldset>
      </Card>
    </>
  )
}
