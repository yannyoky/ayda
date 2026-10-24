import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ApiError, type Schemas } from '../api/client'
import { useConversation, useDeleteMessage, useEditMessage, useHideConversation, useMarkRead, useMe, useMessages, useSendMessage } from '../api/queries'
import { uploadVoice } from '../api/media'
import { MeetupSheet } from '../features/chat/MeetupSheet'
import { VoiceMessage } from '../features/chat/VoiceMessage'
import { canRecordVoice, formatSeconds, useVoiceRecorder } from '../features/chat/useVoiceRecorder'
import { t } from '../i18n'
import { useRealtimeStatus } from '../realtime/realtime'
import { useBackButton } from '../telegram/useBackButton'
import { haptic } from '../telegram/webapp'
import { Avatar } from '../ui/Avatar'
import { Icon } from '../ui/Icon'
import { InlineError, Splash } from '../ui/states'

interface Pending {
  client_id: string
  text: string
  failed: boolean
  /** A recording to upload first; kept until the message is saved so a retry can resend it. */
  voice?: Blob
  attachment_id?: string
}

const timeFormat = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' })
const COOP_CHAT_TTL_MS = 30 * 24 * 3600 * 1000
const EDIT_WINDOW_MS = 24 * 3600 * 1000
const dayFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' })

/** US-17: one chat. Messages arrive over Centrifugo, or by polling when realtime is off. */
export function ChatScreen() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const back = useCallback(() => navigate('/chats'), [navigate])
  useBackButton(back)
  const realtime = useRealtimeStatus()
  const me = useMe()
  const conversation = useConversation(id)
  const messages = useMessages(id, { poll: realtime !== 'live' })
  const send = useSendMessage(id)
  const remove = useDeleteMessage(id)
  const edit = useEditMessage(id)
  const [editing, setEditing] = useState<Schemas['Message'] | null>(null)
  const markRead = useMarkRead(id)
  const hide = useHideConversation(id)
  const [openedAt] = useState(() => Date.now())
  const inputId = useId()
  const [text, setText] = useState('')
  const [pending, setPending] = useState<Pending[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [organizing, setOrganizing] = useState(false)
  const recorder = useVoiceRecorder()
  const [canRecord] = useState(canRecordVoice)
  const end = useRef<HTMLDivElement>(null)
  const readUpTo = useRef(0)

  // Pages come newest first; show oldest at the top
  const saved = useMemo(() => (messages.data?.pages.flatMap((p) => p.items) ?? []).slice().reverse(), [messages.data])
  const savedIds = useMemo(() => new Set(saved.map((m) => m.client_id)), [saved])
  const shown = pending.filter((p) => !savedIds.has(p.client_id))
  const newest = saved.at(-1)?.id ?? 0

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' })
  }, [newest, shown.length])

  const lastRead = conversation.data?.last_read_message_id ?? 0
  const { mutate: mark } = markRead
  useEffect(() => {
    if (newest > Math.max(lastRead, readUpTo.current)) {
      readUpTo.current = newest
      mark(newest)
    }
  }, [newest, lastRead, mark])

  function fail(item: Pending) {
    setPending((cur) => cur.map((p) => (p.client_id === item.client_id ? { ...p, failed: true } : p)))
  }

  async function deliver(item: Pending) {
    setPending((cur) => [...cur.filter((p) => p.client_id !== item.client_id), { ...item, failed: false }])
    let attachmentId = item.attachment_id
    if (item.voice && !attachmentId) {
      try {
        attachmentId = await uploadVoice(id, item.voice)
      } catch (e) {
        fail(item)
        if (e instanceof ApiError && e.status === 429) setNotice(t.chats.tooMany)
        return
      }
      const uploaded = { ...item, attachment_id: attachmentId, failed: false }
      setPending((cur) => cur.map((p) => (p.client_id === uploaded.client_id ? uploaded : p)))
    }
    const body = attachmentId ? { client_id: item.client_id, attachment_id: attachmentId } : { text: item.text, client_id: item.client_id }
    send.mutate(
      body,
      {
        onSuccess: () => haptic('tap'),
        onError: (e) => {
          fail(item)
          if (e instanceof ApiError && e.status === 429) setNotice(t.chats.tooMany)
          if (e instanceof ApiError && e.status === 403) void conversation.refetch()
        },
      },
    )
  }

  function startEdit(m: Schemas['Message']) {
    setSelected(null)
    setEditing(m)
    setText(m.text)
  }

  function cancelEdit() {
    setEditing(null)
    setText('')
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const value = text.trim()
    if (!value) return
    if (editing) {
      const target = editing
      setEditing(null)
      setText('')
      if (value === target.text) return
      edit.mutate(
        { message_id: target.id, text: value },
        { onError: (err) => setNotice(err instanceof ApiError && err.status === 409 ? t.chats.editTooLate : t.chats.failed) },
      )
      return
    }
    setText('')
    setNotice(null)
    void deliver({ client_id: crypto.randomUUID(), text: value, failed: false })
  }

  async function recordVoice() {
    setNotice(null)
    const blob = await recorder.start()
    if (blob) void deliver({ client_id: crypto.randomUUID(), text: '', failed: false, voice: blob })
  }

  function deleteMessage(m: Schemas['Message']) {
    if (!window.confirm(t.chats.deleteConfirm)) return
    setSelected(null)
    remove.mutate(m.id)
  }

  function hideChat() {
    if (!window.confirm(t.chats.hideConfirm)) return
    hide.mutate(undefined, { onSuccess: () => navigate('/chats') })
  }

  if (conversation.isError) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-3 p-4">
        <InlineError onRetry={() => void conversation.refetch()} />
      </main>
    )
  }
  const chat = conversation.data
  if (!chat) return <Splash />

  return (
    <main className="mx-auto flex h-dvh max-w-[480px] flex-col">
      <header className="flex items-center gap-3 px-4 pt-[max(16px,env(safe-area-inset-top))] pb-3">
        <button type="button" aria-label={t.chats.back} onClick={back} className="flex size-11 items-center justify-center rounded-full bg-surface">
          <Icon name="back" size={20} />
        </button>
        <Avatar user={chat.peer ?? { first_name: chat.title }} size={40} />
        <h1 className="m-0 min-w-0 flex-1 truncate font-display text-lg font-bold">{chat.title}</h1>
        {chat.can_send && (
          <button type="button" onClick={() => setOrganizing(true)} className="h-11 shrink-0 rounded-full bg-accent px-4 text-sm font-extrabold text-on-accent">
            {t.meetup.button}
          </button>
        )}
        <button type="button" aria-label={t.chats.hide} onClick={hideChat} disabled={hide.isPending} className="flex size-11 shrink-0 items-center justify-center rounded-full bg-surface">
          <Icon name="trash" size={18} />
        </button>
      </header>
      {/* Shown once the quest is over: the chat is deleted 30 days after that */}
      {chat.deletes_at && Date.parse(chat.deletes_at) - openedAt < COOP_CHAT_TTL_MS && (
        <p role="note" className="m-0 mx-4 mb-2 rounded-field bg-surface px-3.5 py-2 text-xs font-bold text-muted">
          {t.chats.deletesAt(dayFormat.format(new Date(chat.deletes_at)))}
        </p>
      )}
      {organizing && <MeetupSheet conversationId={id} onClose={() => setOrganizing(false)} />}
      <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto px-4 pb-3" aria-live="polite">
        {messages.hasNextPage && (
          <button
            type="button"
            onClick={() => void messages.fetchNextPage()}
            disabled={messages.isFetchingNextPage}
            className="mx-auto my-2 h-10 rounded-field bg-surface px-4 text-sm font-bold"
          >
            {t.chats.older}
          </button>
        )}
        {messages.isError && <InlineError onRetry={() => void messages.refetch()} />}
        {messages.isSuccess && saved.length === 0 && shown.length === 0 && (
          <p className="m-auto text-center text-sm font-semibold text-muted">{t.chats.noMessages}</p>
        )}
        <ul aria-label={chat.title} className="m-0 mt-auto flex list-none flex-col gap-1.5 p-0">
          {saved.map((m) => {
            const mine = m.author.id === me.data?.id
            return (
              <li key={m.id} className={`flex max-w-[80%] flex-col ${mine ? 'items-end self-end' : 'items-start self-start'}`}>
                {chat.kind === 'coop' && !mine && <span className="px-3 text-xs font-bold text-muted">{m.author.first_name}</span>}
                {m.attachment ? (
                  <div
                    className={`flex items-center gap-2 rounded-[20px] px-3 py-2 ${mine ? 'rounded-br-md bg-plate text-on-plate' : 'rounded-bl-md bg-surface text-ink'}`}
                  >
                    <VoiceMessage attachment={m.attachment} mine={mine} onExpired={() => void messages.refetch()} />
                    {mine && (
                      <button type="button" aria-label={t.chats.delete} onClick={() => deleteMessage(m)} className="flex size-8 shrink-0 items-center justify-center rounded-full">
                        <Icon name="trash" size={14} />
                      </button>
                    )}
                    <span className={`text-[11px] font-semibold ${mine ? 'text-on-plate/60' : 'text-muted'}`}>{timeFormat.format(new Date(m.created_at))}</span>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={!mine}
                    onClick={() => setSelected((s) => (s === m.id ? null : m.id))}
                    className={`rounded-[20px] px-3.5 py-2 text-left text-[15px] font-medium break-words whitespace-pre-wrap ${mine ? 'rounded-br-md bg-plate text-on-plate' : 'rounded-bl-md bg-surface text-ink'}`}
                  >
                    {m.text}
                    <span className={`ml-2 inline-block text-[11px] font-semibold ${mine ? 'text-on-plate/60' : 'text-muted'}`}>
                      {m.edited_at && `${t.chats.edited} `}
                      {timeFormat.format(new Date(m.created_at))}
                    </span>
                  </button>
                )}
                {mine && selected === m.id && (
                  <span className="mt-1 flex gap-1.5">
                    {openedAt - Date.parse(m.created_at) < EDIT_WINDOW_MS && (
                      <button type="button" onClick={() => startEdit(m)} className="flex h-9 items-center rounded-field bg-surface px-3 text-sm font-bold">
                        {t.chats.edit}
                      </button>
                    )}
                    <button type="button" onClick={() => deleteMessage(m)} className="flex h-9 items-center gap-1.5 rounded-field bg-surface px-3 text-sm font-bold">
                      <Icon name="trash" size={16} />
                      {t.chats.delete}
                    </button>
                  </span>
                )}
              </li>
            )
          })}
          {shown.map((p) => (
            <li key={p.client_id} className="flex max-w-[80%] flex-col items-end self-end">
              <button
                type="button"
                disabled={!p.failed}
                onClick={() => void deliver(p)}
                aria-label={p.failed ? t.chats.failed : p.voice ? t.chats.voiceSending : t.chats.sending}
                className={`rounded-[20px] rounded-br-md px-3.5 py-2 text-left text-[15px] font-medium break-words whitespace-pre-wrap ${p.failed ? 'bg-surface text-ink outline-2 outline-accent' : 'bg-plate text-on-plate opacity-60'}`}
              >
                {p.voice ? (
                  <span className="flex items-center gap-2 font-bold">
                    <Icon name="mic" size={18} />
                    {t.chats.voice}
                  </span>
                ) : (
                  p.text
                )}
              </button>
              {p.failed && <span className="px-2 pt-0.5 text-xs font-bold text-muted">{t.chats.failed}</span>}
            </li>
          ))}
        </ul>
        <div ref={end} />
      </div>
      {notice && (
        <p role="status" className="m-0 px-4 pb-1 text-xs font-semibold text-muted">
          {notice}
        </p>
      )}
      {editing && (
        <p className="m-0 flex items-center justify-between gap-2 px-4 pb-1 text-xs font-bold text-muted">
          <span className="truncate">{t.chats.editing}</span>
          <button type="button" onClick={cancelEdit} aria-label={t.chats.cancelEdit} className="flex size-8 items-center justify-center rounded-full bg-surface">
            <Icon name="close" size={14} />
          </button>
        </p>
      )}
      {recorder.denied && (
        <p role="status" className="m-0 px-4 pb-1 text-xs font-semibold text-muted">
          {t.chats.micDenied}
        </p>
      )}
      {chat.can_send && recorder.state === 'recording' ? (
        <div className="flex items-center gap-2 px-4 pt-1 pb-[max(16px,env(safe-area-inset-bottom))]">
          <button type="button" onClick={recorder.cancel} aria-label={t.chats.cancelRecording} className="flex size-12 shrink-0 items-center justify-center rounded-field bg-surface">
            <Icon name="close" size={18} />
          </button>
          <p role="timer" className="m-0 flex h-12 flex-1 items-center gap-2 rounded-field bg-surface px-4 text-[15px] font-bold">
            <span className="size-2.5 animate-pulse rounded-full bg-accent" aria-hidden />
            {t.chats.recording(formatSeconds(recorder.seconds))}
          </p>
          <button type="button" onClick={recorder.stop} aria-label={t.chats.stopAndSend} className="flex size-12 shrink-0 items-center justify-center rounded-field bg-accent text-on-accent">
            <Icon name="arrow" size={20} strokeWidth={2.4} />
          </button>
        </div>
      ) : chat.can_send ? (
        <form onSubmit={submit} className="flex gap-2 px-4 pt-1 pb-[max(16px,env(safe-area-inset-bottom))]">
          <label htmlFor={inputId} className="sr-only">
            {t.chats.placeholder}
          </label>
          <input
            id={inputId}
            value={text}
            maxLength={2000}
            autoComplete="off"
            placeholder={t.chats.placeholder}
            onChange={(e) => setText(e.target.value)}
            className="h-12 min-w-0 flex-1 rounded-field border-0 bg-surface px-4 text-[15px] font-medium placeholder:text-muted"
          />
          {canRecord && !editing && !text.trim() ? (
            <button
              type="button"
              onClick={() => void recordVoice()}
              disabled={recorder.state !== 'idle'}
              aria-label={t.chats.record}
              className="flex size-12 shrink-0 items-center justify-center rounded-field bg-accent text-on-accent disabled:opacity-40"
            >
              <Icon name="mic" size={20} strokeWidth={2.4} />
            </button>
          ) : (
            <button
              type="submit"
              aria-label={editing ? t.chats.save : t.chats.send}
              disabled={!text.trim()}
              className="flex size-12 shrink-0 items-center justify-center rounded-field bg-accent text-on-accent disabled:opacity-40"
            >
              <Icon name="arrow" size={20} strokeWidth={2.4} />
            </button>
          )}
        </form>
      ) : (
        <p role="note" className="m-0 mx-4 mb-[max(16px,env(safe-area-inset-bottom))] rounded-card bg-surface p-4 text-sm font-semibold text-muted">
          {t.chats.closed}
        </p>
      )}
    </main>
  )
}
