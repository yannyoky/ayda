import { useCallback, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError } from '../api/client'
import { useAnswerCoop, useCoop, useMe, useToday } from '../api/queries'
import { answerErrorText } from '../features/coop/errors'
import { PartsPlan } from '../features/coop/PartsPlan'
import { t } from '../i18n'
import { useBackButton } from '../telegram/useBackButton'
import { haptic } from '../telegram/webapp'
import { Avatar } from '../ui/Avatar'
import { Icon } from '../ui/Icon'
import { CategoryIcon } from '../ui/quest'
import { FullScreen, InlineError, PrimaryButton, Splash } from '../ui/states'

/** US-18: one co-op quest: who is in, who has done it, the bonus, the shared chat. */
export function CoopScreen() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const back = useCallback(() => navigate('/'), [navigate])
  useBackButton(back)
  const coop = useCoop(id)
  const me = useMe()
  const today = useToday()
  const answer = useAnswerCoop()
  const [openedAt] = useState(() => Date.now())

  if (coop.isPending) return <Splash />
  if (coop.isError) {
    if (coop.error instanceof ApiError && coop.error.status === 404) {
      return <FullScreen title={t.coop.notFound} action={<PrimaryButton onClick={back}>{t.complete.toToday}</PrimaryButton>} />
    }
    return (
      <main className="mx-auto max-w-[480px] p-4">
        <InlineError onRetry={() => void coop.refetch()} />
      </main>
    )
  }

  const c = coop.data
  const myQuest = today.data?.quests.find((q) => q.id === c.my_quest_id)
  const over = Date.parse(c.expires_at) <= openedAt

  function respond(accept: boolean) {
    answer.mutate({ id: c.id, accept }, { onSuccess: () => accept && haptic('success') })
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-3 px-4 pt-[max(16px,env(safe-area-inset-top))] pb-8">
      <header className="flex items-center gap-3">
        <button type="button" aria-label={t.chats.back} onClick={back} className="flex size-11 items-center justify-center rounded-full bg-surface">
          <Icon name="back" size={20} />
        </button>
        <span className="text-sm font-bold text-muted">{t.coop.eyebrow}</span>
      </header>

      <section className="flex flex-col gap-3 rounded-card bg-accent p-5 text-on-accent">
        <div className="flex items-center gap-3">
          <CategoryIcon category={c.category} dark />
          <div className="flex min-w-0 flex-col gap-0.5">
            <h1 className="m-0 font-display text-xl leading-tight font-bold">{c.title}</h1>
            <span className="text-sm font-bold">
              {t.quest.minutes(c.duration_min)} · {t.coop.invitedBy(c.owner.first_name)}
            </span>
          </div>
        </div>
        {c.kind !== 'parts' && (c.place || c.starts_at) && (
          <p className="m-0 rounded-[14px] bg-surface px-3 py-2 text-sm font-extrabold text-ink">
            {[c.starts_at ? t.meetup.when(new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(new Date(c.starts_at))) : null, c.place?.name, c.place?.address]
              .filter(Boolean)
              .join(' · ')}
          </p>
        )}
        <p className="m-0 rounded-[14px] bg-surface px-3 py-2 text-sm font-extrabold text-ink">{c.bonus_awarded ? t.coop.bonusDone : t.coop.rule}</p>
      </section>

      <section aria-labelledby="coop-people" className="flex flex-col rounded-card bg-surface p-4">
        <h2 id="coop-people" className="m-0 pb-1.5 font-display text-base font-bold">
          {t.coop.participants}
        </h2>
        <ul className="m-0 list-none p-0">
          {c.participants.map((p) => {
            const isMe = p.user.id === me.data?.id
            return (
              <li key={p.user.id} className="flex items-center gap-3 border-t border-bg py-2.5 first:border-t-0">
                <Avatar user={p.user} size={40} />
                <span className="min-w-0 flex-1 truncate text-[15px] font-bold">{isMe ? t.coop.you(p.user.first_name) : p.user.first_name}</span>
                {p.completed ? (
                  <span className="flex items-center gap-1 rounded-[10px] bg-plate px-2.5 py-1 text-xs font-extrabold text-on-plate">
                    <Icon name="check" size={14} strokeWidth={3} />
                    {t.coop.done}
                  </span>
                ) : (
                  <span className={`text-xs font-bold ${p.status === 'declined' ? 'text-muted line-through' : 'text-muted'}`}>{t.coop.status[p.status]}</span>
                )}
              </li>
            )
          })}
        </ul>
      </section>

      {c.kind === 'parts' && c.my_status !== 'invited' && c.my_status !== 'declined' && <PartsPlan coop={c} meId={me.data?.id} />}

      {answer.isError && (
        <p role="alert" className="m-0 rounded-card bg-surface p-4 text-sm font-bold">
          {answerErrorText(answer.error)}
        </p>
      )}

      <div className="mt-auto flex flex-col gap-2">
        {c.my_status === 'invited' &&
          (over ? (
            <p className="m-0 text-center text-sm font-bold text-muted">{t.coop.over}</p>
          ) : (
            <div className="flex gap-2">
              <PrimaryButton className="flex-1 !bg-accent !text-on-accent" disabled={answer.isPending} onClick={() => respond(true)}>
                {t.coop.accept}
              </PrimaryButton>
              <button
                type="button"
                disabled={answer.isPending}
                onClick={() => respond(false)}
                className="h-14 flex-1 rounded-[20px] bg-surface text-base font-extrabold disabled:opacity-50"
              >
                {t.coop.decline}
              </button>
            </div>
          ))}
        {c.my_status === 'declined' && <p className="m-0 text-center text-sm font-bold text-muted">{t.coop.declined}</p>}
        {c.kind !== 'parts' && myQuest?.state === 'taken' && (
          <PrimaryButton onClick={() => navigate(`/quest/${myQuest.id}/done`)}>{t.coop.complete}</PrimaryButton>
        )}
        {c.conversation_id && (
          <Link
            to={`/chats/${c.conversation_id}`}
            className="flex h-14 items-center justify-center gap-2 rounded-[20px] bg-surface text-base font-extrabold text-ink no-underline"
          >
            <Icon name="chat" size={20} />
            {t.coop.toChat}
          </Link>
        )}
      </div>
    </main>
  )
}
