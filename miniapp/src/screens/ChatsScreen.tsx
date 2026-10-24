import { Link, useNavigate } from 'react-router'
import { useConversations, useFriends, useMe, useOpenDirect } from '../api/queries'
import { formatAgo, t } from '../i18n'
import { useRealtimeStatus } from '../realtime/realtime'
import { haptic } from '../telegram/webapp'
import { Avatar } from '../ui/Avatar'
import { ScreenHeader } from '../ui/primitives'
import { InlineError } from '../ui/states'

/** US-17: chats with friends, latest first, with unread counts; a row of friends to start one. */
export function ChatsScreen() {
  const realtime = useRealtimeStatus()
  const conversations = useConversations({ poll: realtime !== 'live' })
  const friends = useFriends()
  const me = useMe()
  const open = useOpenDirect()
  const navigate = useNavigate()
  const items = conversations.data?.items ?? []
  const friendList = friends.data?.items ?? []

  function write(userId: string) {
    haptic('tap')
    open.mutate(userId, { onSuccess: (c) => navigate(`/chats/${c.id}`) })
  }

  return (
    <>
      <ScreenHeader title={t.chats.title} />
      {friendList.length > 0 && (
        <section aria-labelledby="chat-start" className="flex flex-col gap-3 rounded-card bg-surface p-4">
          <h2 id="chat-start" className="m-0 font-display text-base font-bold">
            {t.chats.startTitle}
          </h2>
          <ul className="-mx-1 m-0 flex list-none gap-2 overflow-x-auto p-0 px-1 pb-1">
            {friendList.map((f) => (
              <li key={f.id}>
                <button
                  type="button"
                  aria-label={t.chats.writeTo(f.first_name)}
                  disabled={open.isPending}
                  onClick={() => write(f.id)}
                  className="flex w-16 flex-col items-center gap-1.5 rounded-tile p-1 disabled:opacity-60"
                >
                  <Avatar user={f} size={48} />
                  <span className="w-full truncate text-center text-xs font-bold">{f.first_name}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {conversations.isError && <InlineError onRetry={() => void conversations.refetch()} />}
      {conversations.isSuccess && items.length === 0 && (
        <p className="m-0 rounded-card bg-surface p-4 text-[15px] font-semibold text-muted">
          {friendList.length > 0 ? t.chats.empty : t.chats.noFriends}
        </p>
      )}
      {items.length > 0 && (
        <ul aria-label={t.chats.title} className="m-0 flex list-none flex-col overflow-hidden rounded-card bg-surface p-0">
          {items.map((c) => {
            const last = c.last_message
            const mine = last?.author.id === me.data?.id
            return (
              <li key={c.id} className="border-t border-bg first:border-t-0">
                <Link to={`/chats/${c.id}`} className="flex items-center gap-3 p-4 text-ink no-underline">
                  <Avatar user={c.peer ?? { first_name: c.title }} size={44} />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-[15px] font-bold">{c.title}</span>
                      <span className="shrink-0 text-xs font-semibold text-muted">{formatAgo(c.updated_at)}</span>
                    </span>
                    <span className="flex items-center justify-between gap-2">
                      <span className={`truncate text-sm ${c.unread_count > 0 ? 'font-bold text-ink' : 'font-medium text-muted'}`}>
                        {last ? `${mine ? t.chats.you : ''}${last.attachment ? `🎤 ${t.chats.voice}` : last.text}` : t.chats.noMessages}
                      </span>
                      {c.unread_count > 0 && (
                        <span
                          aria-label={t.chats.unread(c.unread_count)}
                          className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-accent px-1.5 text-xs font-extrabold text-on-accent"
                        >
                          {c.unread_count}
                        </span>
                      )}
                    </span>
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </>
  )
}
