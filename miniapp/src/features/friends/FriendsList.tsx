import { useState } from 'react'
import { useCreateInvite, useFriends, useRemoveFriend } from '../../api/queries'
import { t } from '../../i18n'
import { shareLink } from '../../telegram/webapp'
import { Avatar } from '../../ui/Avatar'
import { Icon } from '../../ui/Icon'

const sinceFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' })

/** US-12: friends, a reusable 7-day invite link shared through Telegram, removing a friend. */
export function FriendsList() {
  const friends = useFriends()
  const invite = useCreateInvite()
  const remove = useRemoveFriend()
  const [shared, setShared] = useState(false)
  const items = friends.data?.items ?? []

  function share() {
    invite.mutate(undefined, {
      onSuccess: (inv) => {
        shareLink(inv.url, t.friends.inviteText)
        setShared(true)
      },
    })
  }

  return (
    <section aria-labelledby="friends-title" className="flex flex-col gap-3 rounded-card bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 id="friends-title" className="m-0 font-display text-base font-bold">
          {t.friends.listTitle} {items.length > 0 && <span className="text-muted">{items.length}</span>}
        </h2>
      </div>
      <button
        type="button"
        onClick={share}
        disabled={invite.isPending}
        className="flex h-12 items-center justify-center gap-2 rounded-field bg-accent text-[15px] font-extrabold text-on-accent disabled:opacity-60"
      >
        <Icon name="share" size={18} strokeWidth={2.2} />
        {t.friends.invite}
      </button>
      {shared && (
        <p role="status" className="m-0 text-xs font-semibold text-muted">
          {t.friends.inviteShared}
        </p>
      )}
      {items.length > 0 && (
        <ul className="m-0 flex list-none flex-col p-0">
          {items.map((f) => (
            <li key={f.id} className="flex items-center gap-3 border-t border-bg py-2 first:border-t-0">
              <Avatar user={f} size={36} />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[15px] font-bold">{f.first_name}</span>
                <span className="text-xs font-semibold text-muted">{t.friends.since(sinceFormat.format(new Date(f.since)))}</span>
              </span>
              <button
                type="button"
                aria-label={t.friends.remove(f.first_name)}
                onClick={() => {
                  if (window.confirm(t.friends.removeConfirm(f.first_name))) remove.mutate(f.id)
                }}
                className="flex size-10 items-center justify-center rounded-tile text-muted"
              >
                <Icon name="close" size={18} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
