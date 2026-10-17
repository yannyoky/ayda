import { Link } from 'react-router'
import { useAnswerCoop, useCoops } from '../../api/queries'
import { t } from '../../i18n'
import { haptic } from '../../telegram/webapp'
import { Avatar } from '../../ui/Avatar'
import { answerErrorText } from './errors'

/** US-18: invitations to co-op quests on the Today screen. */
export function CoopInvites() {
  const coops = useCoops()
  const answer = useAnswerCoop()
  const invites = (coops.data?.items ?? []).filter((c) => c.my_status === 'invited')
  if (invites.length === 0) return null
  return (
    <section aria-labelledby="coop-invites" className="flex flex-col gap-2 rounded-card bg-surface p-4">
      <h2 id="coop-invites" className="m-0 font-display text-base font-bold">
        {t.coop.invitesTitle}
      </h2>
      <p className="m-0 text-xs font-semibold text-muted">{t.coop.rule}</p>
      <ul className="m-0 flex list-none flex-col p-0">
        {invites.map((c) => (
          <li key={c.id} className="flex flex-col gap-2.5 border-t border-bg py-3 first:border-t-0">
            <Link to={`/coops/${c.id}`} className="flex items-center gap-3 text-ink no-underline">
              <Avatar user={c.owner} size={40} />
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-xs font-bold text-muted">{t.coop.invitedBy(c.owner.first_name)}</span>
                <span className="truncate text-[15px] font-bold">{c.title}</span>
                <span className="text-xs font-semibold text-muted">{t.quest.minutes(c.duration_min)}</span>
              </span>
            </Link>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={answer.isPending}
                onClick={() => answer.mutate({ id: c.id, accept: true }, { onSuccess: () => haptic('success') })}
                className="h-10 flex-1 rounded-field bg-accent text-sm font-extrabold text-on-accent disabled:opacity-60"
              >
                {t.coop.accept}
              </button>
              <button
                type="button"
                disabled={answer.isPending}
                onClick={() => answer.mutate({ id: c.id, accept: false })}
                className="h-10 flex-1 rounded-field bg-bg text-sm font-extrabold disabled:opacity-60"
              >
                {t.coop.decline}
              </button>
            </div>
          </li>
        ))}
      </ul>
      {answer.isError && (
        <p role="alert" className="m-0 text-sm font-bold">
          {answerErrorText(answer.error)}
        </p>
      )}
    </section>
  )
}
