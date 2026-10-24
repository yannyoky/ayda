import { useState, type ReactNode } from 'react'
import type { Schemas } from '../../api/client'
import { useCompleteOnboarding, useMe, useSetInterests, useUpdateProfile } from '../../api/queries'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'
import { InlineError, PrimaryButton } from '../../ui/states'
import { CityPicker } from '../profile/CityPicker'
import { InterestsPicker, type InterestSelection } from '../profile/InterestsPicker'
import { HabitsEditor } from '../profile/HabitsEditor'
import { RemindersEditor } from '../profile/RemindersEditor'
import { ThemePicker } from '../profile/ThemePicker'

const STEPS = ['city', 'interests', 'habits', 'reminders', 'theme'] as const
type Step = (typeof STEPS)[number]

/** US-02: city (required), interests, own habits, reminder times and theme; everything else can be skipped. */
export function Onboarding() {
  const me = useMe().data as Schemas['Me']
  const [step, setStep] = useState<Step>('city')
  const [interests, setInterests] = useState<InterestSelection>({ codes: [], tags: [] })
  const [reminders, setReminders] = useState<Schemas['Reminders']>(me.reminders)
  const updateProfile = useUpdateProfile()
  const saveInterests = useSetInterests()
  const complete = useCompleteOnboarding()
  const index = STEPS.indexOf(step)
  const failed = updateProfile.isError || saveInterests.isError || complete.isError
  const busy = updateProfile.isPending || saveInterests.isPending || complete.isPending

  const advance = () => {
    const next = STEPS[index + 1]
    if (next) setStep(next)
    else complete.mutate()
  }

  async function next() {
    if (step === 'interests') await saveInterests.mutateAsync(interests)
    if (step === 'reminders') await updateProfile.mutateAsync({ reminders })
    advance()
  }

  const content: Record<Step, { title: string; text: string; body: ReactNode; skippable: boolean; ready: boolean }> = {
    city: {
      title: t.onboarding.city.title,
      text: t.onboarding.city.text,
      body: <CityPicker selected={me.city ?? null} onPick={(city) => updateProfile.mutate({ city_id: city.id })} />,
      skippable: false,
      ready: Boolean(me.city),
    },
    interests: {
      title: t.onboarding.interests.title,
      text: t.onboarding.interests.text,
      body: <InterestsPicker value={interests} onChange={setInterests} />,
      skippable: true,
      ready: true,
    },
    habits: { title: t.onboarding.habits.title, text: t.onboarding.habits.text, body: <HabitsEditor />, skippable: true, ready: true },
    reminders: {
      title: t.onboarding.reminders.title,
      text: t.onboarding.reminders.text,
      body: <RemindersEditor value={reminders} onChange={setReminders} />,
      skippable: true,
      ready: true,
    },
    theme: {
      title: t.onboarding.theme.title,
      text: t.onboarding.theme.text,
      body: <ThemePicker value={me.theme} onChange={(theme) => updateProfile.mutate({ theme })} />,
      skippable: false,
      ready: true,
    },
  }
  const current = content[step]
  const last = index === STEPS.length - 1

  return (
    <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-4 px-4 pt-[max(20px,env(safe-area-inset-top))] pb-8">
      <div className="flex items-center gap-3">
        {index > 0 ? (
          <button
            type="button"
            aria-label={t.onboarding.back}
            onClick={() => setStep(STEPS[index - 1]!)}
            className="flex size-11 shrink-0 items-center justify-center rounded-full bg-surface"
          >
            <Icon name="back" size={20} />
          </button>
        ) : (
          <span className="size-11 shrink-0" />
        )}
        <div
          role="progressbar"
          aria-label={t.onboarding.progress(index + 1, STEPS.length)}
          aria-valuemin={1}
          aria-valuemax={STEPS.length}
          aria-valuenow={index + 1}
          className="flex flex-1 gap-1.5"
        >
          {STEPS.map((s, i) => (
            <span key={s} className={`h-1.5 flex-1 rounded-full ${i <= index ? 'bg-ink' : 'bg-track'}`} />
          ))}
        </div>
      </div>
      <header className="flex flex-col gap-1 px-1">
        <h1 className="m-0 font-display text-[26px] font-bold tracking-[-0.5px]">{current.title}</h1>
        <p className="m-0 text-[15px] font-medium text-muted">{current.text}</p>
      </header>
      {current.body}
      {failed && <InlineError />}
      <div className="mt-auto flex gap-2 pt-2">
        {current.skippable && (
          <button type="button" onClick={advance} disabled={busy} className="h-14 rounded-[20px] bg-surface px-5 text-sm font-extrabold">
            {t.onboarding.skip}
          </button>
        )}
        <PrimaryButton disabled={!current.ready || busy} onClick={() => void next().catch(() => undefined)} className="flex-1">
          {last ? t.onboarding.finish : t.onboarding.next}
          <Icon name="arrow" size={20} strokeWidth={2.4} />
        </PrimaryButton>
      </div>
    </main>
  )
}
