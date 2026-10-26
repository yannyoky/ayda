import { useState } from 'react'
import { useNavigate } from 'react-router'
import type { Schemas } from '../../api/client'
import { useAnswerHandoff, useOfferHandoff, useSetCoopItem, useWithdrawHandoff } from '../../api/queries'
import { t } from '../../i18n'
import { Avatar } from '../../ui/Avatar'
import { Icon } from '../../ui/Icon'
import { partErrorText } from './errors'

/** The parts of a shared plan: who does what, the live checklist and hand-offs (ADR 0010). */
export function PartsPlan({ coop, meId }: { coop: Schemas['Coop']; meId: string | undefined }) {
  const setItem = useSetCoopItem()
  const offer = useOfferHandoff()
  const withdraw = useWithdrawHandoff()
  const answer = useAnswerHandoff()
  const failed = [setItem, offer, withdraw, answer].find((m) => m.isError)

  return (
    <section aria-labelledby="coop-plan" className="flex flex-col gap-3">
      <h2 id="coop-plan" className="m-0 font-display text-base font-bold">
        {t.coop.plan.title}
      </h2>
      {(coop.parts ?? []).map((part) => (
        <Part
          key={part.id}
          coop={coop}
          part={part}
          mine={part.assignee.id === meId}
          onTick={(itemId, done) => setItem.mutate({ coopId: coop.id, partId: part.id, itemId, done })}
          onOffer={(friendId) => offer.mutate({ coopId: coop.id, partId: part.id, friendId })}
          onWithdraw={() => withdraw.mutate({ coopId: coop.id, partId: part.id })}
          onAnswer={(accept) => answer.mutate({ coopId: coop.id, partId: part.id, accept })}
        />
      ))}
      {failed?.error && (
        <p role="alert" className="m-0 rounded-card bg-surface p-4 text-sm font-bold">
          {partErrorText(failed.error)}
        </p>
      )}
    </section>
  )
}

function Part({
  coop,
  part,
  mine,
  onTick,
  onOffer,
  onWithdraw,
  onAnswer,
}: {
  coop: Schemas['Coop']
  part: Schemas['CoopPart']
  mine: boolean
  onTick: (itemId: string, done: boolean) => void
  onOffer: (friendId: string) => void
  onWithdraw: () => void
  onAnswer: (accept: boolean) => void
}) {
  const navigate = useNavigate()
  const [choosing, setChoosing] = useState(false)
  const heading = `part-${part.id}`
  const handoff = part.handoff
  const others = coop.participants.filter((p) => (p.status === 'owner' || p.status === 'accepted') && p.user.id !== part.assignee.id)
  const canTick = mine && part.state === 'open'

  return (
    <article aria-labelledby={heading} className={`flex flex-col gap-2.5 rounded-card bg-surface p-4 ${part.state === 'done' ? 'opacity-70' : ''}`}>
      <div className="flex items-center gap-3">
        <Avatar user={part.assignee} size={36} />
        <div className="flex min-w-0 flex-1 flex-col">
          <h3 id={heading} className="m-0 truncate font-display text-[15px] font-bold">
            {part.title}
          </h3>
          <span className="text-xs font-bold text-muted">{mine ? t.coop.plan.you : t.coop.plan.assignee(part.assignee.first_name)}</span>
        </div>
        <span className="shrink-0 rounded-chip bg-bg px-2.5 py-1 text-xs font-extrabold">{t.coop.plan.state[part.state]}</span>
      </div>

      {part.place && (
        <p className="m-0 text-sm font-semibold text-muted">
          {part.place.name}
          {part.place.address ? `, ${part.place.address}` : ''}
        </p>
      )}
      {part.state === 'locked' && <p className="m-0 text-sm font-semibold text-muted">{t.coop.plan.afterPrevious}</p>}

      {part.items.length > 0 && (
        <ul aria-label={t.coop.plan.list(part.title)} className="m-0 flex list-none flex-col p-0">
          {part.items.map((item) => (
            <li key={item.id}>
              <label className="flex min-h-11 items-center gap-3 text-[15px] font-semibold">
                <input
                  type="checkbox"
                  checked={item.done}
                  disabled={!canTick}
                  onChange={(e) => onTick(item.id, e.target.checked)}
                  className="size-5 shrink-0 accent-[var(--color-ink)]"
                />
                <span className={item.done ? 'text-muted line-through' : ''}>{item.text}</span>
              </label>
            </li>
          ))}
        </ul>
      )}

      {handoff?.for_me && (
        <div className="flex flex-col gap-2 rounded-tile bg-bg p-3">
          <p className="m-0 text-sm font-extrabold">{t.coop.plan.incoming(part.assignee.first_name)}</p>
          <div className="flex gap-2">
            <button type="button" onClick={() => onAnswer(true)} className="h-11 flex-1 rounded-field bg-plate text-sm font-extrabold text-on-plate">
              {t.coop.plan.acceptPart}
            </button>
            <button type="button" onClick={() => onAnswer(false)} className="h-11 flex-1 rounded-field bg-surface text-sm font-extrabold">
              {t.coop.plan.declinePart}
            </button>
          </div>
        </div>
      )}

      {mine && part.state !== 'done' && handoff && !handoff.for_me && (
        <div className="flex items-center justify-between gap-3">
          <p className="m-0 text-sm font-semibold text-muted">{t.coop.plan.offered(handoff.to.first_name)}</p>
          <button type="button" onClick={onWithdraw} className="h-11 shrink-0 rounded-field bg-bg px-4 text-sm font-extrabold">
            {t.coop.plan.withdraw}
          </button>
        </div>
      )}

      {mine && part.state !== 'done' && !handoff && (
        <>
          {choosing ? (
            <div role="group" aria-label={t.coop.plan.handOff} className="flex flex-col gap-1.5">
              {others.length === 0 && <p className="m-0 text-sm font-semibold text-muted">{t.coop.plan.noOneToHandOff}</p>}
              {others.map((p) => (
                <button
                  key={p.user.id}
                  type="button"
                  onClick={() => {
                    onOffer(p.user.id)
                    setChoosing(false)
                  }}
                  className="flex h-11 items-center gap-3 rounded-field bg-bg px-3 text-sm font-extrabold"
                >
                  <Avatar user={p.user} size={28} />
                  {t.coop.plan.handOffTo(p.user.first_name)}
                </button>
              ))}
            </div>
          ) : (
            <button type="button" onClick={() => setChoosing(true)} className="h-11 self-start rounded-field bg-bg px-4 text-sm font-extrabold">
              {t.coop.plan.handOff}
            </button>
          )}
        </>
      )}

      {part.my_quest_id && (
        <button
          type="button"
          onClick={() => navigate(`/quest/${part.my_quest_id}/done`)}
          className="flex h-12 items-center justify-center gap-2 rounded-field bg-plate text-sm font-extrabold text-on-plate"
        >
          <Icon name="check" size={18} strokeWidth={3} />
          {t.coop.plan.complete}
        </button>
      )}
    </article>
  )
}
