import { useState } from 'react'
import { useNavigate } from 'react-router'
import { ApiError, type Schemas } from '../../api/client'
import { useCreateCoop, useFriends } from '../../api/queries'
import { t } from '../../i18n'
import { haptic } from '../../telegram/webapp'
import { Avatar } from '../../ui/Avatar'
import { Icon } from '../../ui/Icon'
import { Sheet } from '../../ui/Sheet'
import { PrimaryButton } from '../../ui/states'

const MAX_FRIENDS = 3

/** US-18: invite 1-3 friends to a taken quest; each does it on their own. */
export function CoopSheet({ quest, onClose }: { quest: Schemas['DayQuest']; onClose: () => void }) {
  const friends = useFriends()
  const create = useCreateCoop()
  const navigate = useNavigate()
  const [picked, setPicked] = useState<string[]>([])
  const items = friends.data?.items ?? []

  function toggle(id: string) {
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < MAX_FRIENDS ? [...p, id] : p))
  }

  function submit() {
    create.mutate(
      { questId: quest.id, friendIds: picked },
      {
        onSuccess: (coop) => {
          haptic('success')
          onClose()
          navigate(`/coops/${coop.id}`)
        },
      },
    )
  }

  return (
    <Sheet title={t.coop.sheetTitle} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <span className="font-display text-base font-bold">{quest.title}</span>
          <span className="text-sm font-semibold text-muted">{t.coop.sheetHint}</span>
        </div>
        {friends.isSuccess && items.length === 0 ? (
          <p className="m-0 text-sm font-bold text-muted">{t.coop.noFriends}</p>
        ) : (
          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
            <legend className="mb-2 text-sm font-bold">{t.coop.pickFriends}</legend>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {items.map((f) => {
                const on = picked.includes(f.id)
                return (
                  <li key={f.id}>
                    <label className="flex items-center gap-3 rounded-field bg-surface p-2.5 has-[:focus-visible]:outline-2">
                      <input
                        type="checkbox"
                        checked={on}
                        disabled={!on && picked.length >= MAX_FRIENDS}
                        onChange={() => toggle(f.id)}
                        className="sr-only"
                      />
                      <Avatar user={f} size={36} />
                      <span className="flex-1 text-[15px] font-bold">{f.first_name}</span>
                      <span
                        aria-hidden="true"
                        className={`flex size-6 items-center justify-center rounded-full ${on ? 'bg-accent text-on-accent' : 'bg-bg'}`}
                      >
                        {on && <Icon name="check" size={14} strokeWidth={3} />}
                      </span>
                    </label>
                  </li>
                )
              })}
            </ul>
          </fieldset>
        )}
        {create.isError && (
          <p role="alert" className="m-0 text-sm font-bold">
            {create.error instanceof ApiError ? (create.error.problem?.detail ?? create.error.message) : create.error.message}
          </p>
        )}
        <PrimaryButton type="button" onClick={submit} disabled={picked.length === 0 || create.isPending}>
          {t.coop.send(picked.length)}
        </PrimaryButton>
      </div>
    </Sheet>
  )
}
