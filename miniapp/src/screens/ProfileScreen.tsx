import { useState, type ReactNode } from 'react'
import type { Schemas } from '../api/client'
import { useGoalCatalog, useMe, useMyGoals, useMyHabits, useRequestDeletion, useSetGoals, useUpdateProfile } from '../api/queries'
import { CityPicker } from '../features/profile/CityPicker'
import { GoalsPicker } from '../features/profile/GoalsPicker'
import { HabitsEditor } from '../features/profile/HabitsEditor'
import { RemindersEditor } from '../features/profile/RemindersEditor'
import { ThemePicker } from '../features/profile/ThemePicker'
import { t } from '../i18n'
import { Avatar } from '../ui/Avatar'
import { Card } from '../ui/primitives'

type Section = 'city' | 'goals' | 'habits' | 'reminders'

export function ProfileScreen() {
  const me = useMe().data as Schemas['Me']
  const update = useUpdateProfile()
  const [open, setOpen] = useState<Section | null>(null)
  const toggle = (s: Section) => setOpen((cur) => (cur === s ? null : s))

  return (
    <>
      <header className="flex items-center gap-3 px-1">
        <Avatar user={me} size={56} />
        <div className="flex min-w-0 flex-col">
          <h1 className="m-0 truncate font-display text-[26px] font-bold tracking-[-0.5px]">{t.profile.title}</h1>
          <span className="truncate text-sm font-semibold text-muted">
            {[me.first_name, me.last_name].filter(Boolean).join(' ')}
            {me.username ? ` · @${me.username}` : ''}
          </span>
        </div>
      </header>

      <Card>
        <h2 className="m-0 mb-3 font-display text-base font-bold">{t.profile.theme}</h2>
        <ThemePicker value={me.theme} onChange={(theme) => update.mutate({ theme })} />
      </Card>

      <Editable title={t.profile.city} summary={me.city ? `${me.city.name}, ${me.city.region_name}` : t.profile.notSet} open={open === 'city'} onToggle={() => toggle('city')}>
        <CityPicker
          selected={me.city ?? null}
          onPick={(city) => update.mutate({ city_id: city.id }, { onSuccess: () => setOpen(null) })}
        />
      </Editable>

      <GoalsSection open={open === 'goals'} onToggle={() => toggle('goals')} />

      <HabitsSection open={open === 'habits'} onToggle={() => toggle('habits')} />

      <RemindersSection me={me} open={open === 'reminders'} onToggle={() => toggle('reminders')} />

      <PrivacySection />
    </>
  )
}

function Editable({ title, summary, open, onToggle, children }: { title: string; summary: string; open: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-col">
          <h2 className="m-0 font-display text-base font-bold">{title}</h2>
          <span className="truncate text-sm font-semibold text-muted">{summary}</span>
        </div>
        <button type="button" aria-expanded={open} onClick={onToggle} className="h-11 shrink-0 rounded-field bg-bg px-4 text-sm font-extrabold">
          {open ? t.profile.done : t.profile.change}
        </button>
      </div>
      {open && <div className="-mx-1 rounded-card bg-bg p-1">{children}</div>}
    </Card>
  )
}

function GoalsSection({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const mine = useMyGoals()
  const catalog = useGoalCatalog()
  const save = useSetGoals()
  const codes = mine.data?.goal_codes ?? []
  const summary = codes.map((c) => catalog.data?.items.find((g) => g.code === c)?.title ?? c).join(', ') || t.profile.notSet
  return (
    <Editable title={t.profile.goals} summary={summary} open={open} onToggle={onToggle}>
      <div className="p-2">
        <GoalsPicker value={codes} onChange={(next) => save.mutate(next)} />
      </div>
    </Editable>
  )
}

function HabitsSection({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const habits = useMyHabits()
  const items = habits.data?.items ?? []
  const summary = items.map((h) => h.text).join(', ') || t.profile.notSet
  return (
    <Editable title={t.profile.habits} summary={summary} open={open} onToggle={onToggle}>
      <HabitsEditor />
    </Editable>
  )
}

function RemindersSection({ me, open, onToggle }: { me: Schemas['Me']; open: boolean; onToggle: () => void }) {
  const update = useUpdateProfile()
  const r = me.reminders
  const summary = [
    `${t.onboarding.reminders.morning.toLowerCase()} ${r.morning_at ?? t.onboarding.reminders.off.toLowerCase()}`,
    `${t.onboarding.reminders.evening.toLowerCase()} ${r.evening_at ?? t.onboarding.reminders.off.toLowerCase()}`,
  ].join(', ')
  return (
    <Editable title={t.profile.reminders} summary={summary} open={open} onToggle={onToggle}>
      <RemindersEditor value={r} onChange={(reminders) => update.mutate({ reminders })} />
    </Editable>
  )
}

function PrivacySection() {
  const deletion = useRequestDeletion()
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="m-0 font-display text-base font-bold">{t.profile.privacy}</h2>
      <p className="m-0 text-sm font-medium text-muted">{t.consent.storage}</p>
      {deletion.isSuccess ? (
        <p role="status" className="m-0 text-[15px] font-bold">
          {t.profile.deleteDone}
        </p>
      ) : (
        <button
          type="button"
          disabled={deletion.isPending}
          onClick={() => {
            if (window.confirm(t.profile.deleteConfirm)) deletion.mutate()
          }}
          className="h-12 rounded-field border-2 border-track bg-transparent text-sm font-extrabold text-ink"
        >
          {t.profile.deleteAccount}
        </button>
      )}
    </Card>
  )
}
