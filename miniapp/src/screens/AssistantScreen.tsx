import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router'
import { ApiError, type Schemas } from '../api/client'
import { useAssistantThread, useSendAssistantMessage, useTakeQuests, useToday } from '../api/queries'
import { RecipeSheet } from '../features/recipes/RecipeSheet'
import { t } from '../i18n'
import { useBackButton } from '../telegram/useBackButton'
import { haptic } from '../telegram/webapp'
import { Icon } from '../ui/Icon'
import { InlineError, Splash } from '../ui/states'

const MESSAGE_MAX = 1000
const eventWhen = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })

/** The day chat with the assistant (ADR 0013): the check-in opens it, and every quest of the
 * day has its own topic (`?quest=<id>`). Cards carry facts from code: places, recipes, a quest. */
export function AssistantScreen() {
  const [params] = useSearchParams()
  const questId = params.get('quest')
  const navigate = useNavigate()
  const location = useLocation()
  // Opened straight from a link: there is nothing to go back to but Today
  const first = location.key === 'default'
  const back = useCallback(() => (first ? navigate('/') : navigate(-1)), [first, navigate])
  useBackButton(back)
  const today = useToday()
  const thread = useAssistantThread(questId)
  const send = useSendAssistantMessage(questId)
  const inputId = useId()
  const [text, setText] = useState('')
  const [waiting, setWaiting] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [recipeId, setRecipeId] = useState<string | null>(null)
  const end = useRef<HTMLDivElement>(null)

  const quest = questId ? today.data?.quests.find((q) => q.id === questId) : undefined
  const items = thread.data?.items ?? []
  const left = thread.data?.messages_left ?? 0
  const limitHit = send.error instanceof ApiError && send.error.status === 429

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' })
  }, [items.length, waiting])

  function deliver(value: string) {
    setWaiting(value)
    setFailed(null)
    send.mutate(value, {
      onSuccess: () => {
        haptic('tap')
        setWaiting(null)
      },
      onError: () => {
        setWaiting(null)
        setFailed(value)
      },
    })
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const value = text.trim()
    if (!value || send.isPending) return
    setText('')
    deliver(value)
  }

  if (thread.isError) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-3 p-4">
        <InlineError onRetry={() => void thread.refetch()} />
      </main>
    )
  }
  if (!thread.data) return <Splash />

  const hints = questId ? t.assistant.hintsQuest : t.assistant.hints
  const canSend = left > 0 && !limitHit

  return (
    <main className="mx-auto flex h-dvh max-w-[480px] flex-col">
      <header className="flex items-center gap-3 px-4 pt-[max(16px,env(safe-area-inset-top))] pb-3">
        <button type="button" aria-label={t.assistant.back} onClick={back} className="flex size-11 items-center justify-center rounded-full bg-surface">
          <Icon name="back" size={20} />
        </button>
        <div className="flex min-w-0 flex-1 flex-col">
          <h1 className="m-0 truncate font-display text-lg font-bold">{t.assistant.title}</h1>
          {quest && <span className="truncate text-xs font-semibold text-muted">{t.assistant.about(quest.title)}</span>}
        </div>
      </header>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto px-4 pb-3" aria-live="polite">
        {items.length === 0 && !waiting && (
          <p className="m-0 mt-auto rounded-card bg-surface p-4 text-sm font-semibold text-muted">{questId ? t.assistant.emptyQuest : t.assistant.empty}</p>
        )}
        <ul aria-label={t.assistant.title} className="m-0 mt-auto flex list-none flex-col gap-2 p-0">
          {items.map((m) => (
            <li key={m.id} className={`flex flex-col gap-2 ${m.role === 'user' ? 'max-w-[80%] items-end self-end' : 'items-start self-stretch'}`}>
              <p
                className={`m-0 max-w-[85%] rounded-[20px] px-3.5 py-2 text-[15px] font-medium break-words whitespace-pre-wrap ${
                  m.role === 'user' ? 'rounded-br-md bg-plate text-on-plate' : 'rounded-bl-md bg-surface text-ink'
                }`}
              >
                {m.text}
              </p>
              {m.cards.map((card, i) => (
                <AssistantCardView key={i} card={card} onCook={setRecipeId} />
              ))}
            </li>
          ))}
          {waiting && (
            <li className="flex max-w-[80%] flex-col items-end self-end">
              <p className="m-0 rounded-[20px] rounded-br-md bg-plate px-3.5 py-2 text-[15px] font-medium break-words whitespace-pre-wrap text-on-plate opacity-60">
                {waiting}
              </p>
            </li>
          )}
          {send.isPending && (
            <li role="status" className="flex items-center gap-2 self-start rounded-[20px] rounded-bl-md bg-surface px-3.5 py-2.5 text-sm font-semibold text-muted">
              <span aria-hidden="true" className="size-2.5 animate-pulse rounded-full bg-accent" />
              {t.assistant.typing}
            </li>
          )}
        </ul>
        {failed && !limitHit && (
          <div role="alert" className="flex items-center justify-between gap-3 rounded-field bg-surface px-3.5 py-2 text-sm font-bold">
            {t.assistant.failed}
            <button type="button" onClick={() => deliver(failed)} className="h-9 shrink-0 rounded-field bg-plate px-3 text-sm font-extrabold text-on-plate">
              {t.assistant.retry}
            </button>
          </div>
        )}
        <div ref={end} />
      </div>

      {canSend && items.length <= 2 && !send.isPending && (
        <div className="flex gap-2 overflow-x-auto px-4 pb-2">
          {hints.map((hint) => (
            <button key={hint} type="button" onClick={() => deliver(hint)} className="h-9 shrink-0 rounded-full bg-surface px-3.5 text-sm font-bold">
              {hint}
            </button>
          ))}
        </div>
      )}
      {canSend ? (
        <form onSubmit={submit} className="flex flex-col gap-1 px-4 pt-1 pb-[max(16px,env(safe-area-inset-bottom))]">
          <div className="flex gap-2">
            <label htmlFor={inputId} className="sr-only">
              {t.assistant.placeholder}
            </label>
            <input
              id={inputId}
              value={text}
              maxLength={MESSAGE_MAX}
              autoComplete="off"
              placeholder={t.assistant.placeholder}
              onChange={(e) => setText(e.target.value)}
              className="h-12 min-w-0 flex-1 rounded-field border-0 bg-surface px-4 text-[15px] font-medium placeholder:text-muted"
            />
            <button
              type="submit"
              aria-label={t.assistant.send}
              disabled={!text.trim() || send.isPending}
              className="flex size-12 shrink-0 items-center justify-center rounded-field bg-accent text-on-accent disabled:opacity-40"
            >
              <Icon name="arrow" size={20} strokeWidth={2.4} />
            </button>
          </div>
          {left <= 10 && <span className="px-1 text-xs font-semibold text-muted">{t.assistant.left(left)}</span>}
        </form>
      ) : (
        <p role="note" className="m-0 mx-4 mb-[max(16px,env(safe-area-inset-bottom))] rounded-card bg-surface p-4 text-sm font-semibold text-muted">
          {t.assistant.limit}
        </p>
      )}
      {recipeId && <RecipeSheet recipeId={recipeId} onClose={() => setRecipeId(null)} />}
    </main>
  )
}

function AssistantCardView({ card, onCook }: { card: Schemas['AssistantCard']; onCook: (id: string) => void }) {
  return (
    <div className="flex w-full flex-col gap-2">
      {card.note && <p className="m-0 rounded-field bg-surface px-3.5 py-2 text-xs font-bold text-muted">{card.note}</p>}
      {card.places.length > 0 && (
        <ul aria-label={t.assistant.title} className="m-0 flex list-none flex-col gap-2 p-0">
          {card.places.map((p) => (
            <li key={p.id} className="flex flex-col gap-1.5 rounded-card bg-surface p-3.5">
              <span className="text-[15px] font-bold">{p.name}</span>
              <span className="text-xs font-semibold text-muted">
                {[t.assistant.placeKinds[p.kind], p.address, t.assistant.distance(p.distance_m), p.open_now ? t.assistant.openNow : null].filter(Boolean).join(' · ')}
              </span>
              <span className="flex gap-2">
                <a href={p.gis_url} target="_blank" rel="noreferrer" className="flex h-9 items-center gap-1 rounded-field bg-bg px-3 text-xs font-extrabold text-ink no-underline">
                  {t.assistant.on2gis}
                  <Icon name="external" size={14} />
                </a>
                <a href={p.yandex_url} target="_blank" rel="noreferrer" className="flex h-9 items-center gap-1 rounded-field bg-bg px-3 text-xs font-extrabold text-ink no-underline">
                  {t.assistant.onYandex}
                  <Icon name="external" size={14} />
                </a>
              </span>
            </li>
          ))}
        </ul>
      )}
      {card.events.length > 0 && (
        <ul aria-label={t.assistant.eventsTitle} className="m-0 flex list-none flex-col gap-2 p-0">
          {card.events.map((e) => (
            <li key={e.id} className="flex flex-col gap-1.5 rounded-card bg-surface p-3.5">
              <span className="text-[15px] font-bold">{e.title}</span>
              <span className="text-sm font-semibold">{eventWhen.format(new Date(e.starts_at))}</span>
              <span className="text-xs font-semibold text-muted">
                {[e.venue, e.city, t.assistant.eventDistance(e.distance_km), e.is_free ? t.assistant.eventFree : e.price_min ? t.assistant.eventFrom(e.price_min) : null]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
              <a href={e.url} target="_blank" rel="noreferrer" className="flex h-9 w-fit items-center gap-1 rounded-field bg-bg px-3 text-xs font-extrabold text-ink no-underline">
                {t.assistant.eventOpen}
                <Icon name="external" size={14} />
              </a>
            </li>
          ))}
        </ul>
      )}
      {card.recipes.length > 0 && (
        <ul aria-label={t.recipes.title} className="m-0 flex list-none flex-col gap-2 p-0">
          {card.recipes.map((r) => (
            <li key={r.id} className="flex flex-col gap-1.5 rounded-card bg-surface p-3.5">
              <span className="flex items-baseline justify-between gap-3">
                <span className="text-[15px] font-bold">{r.title}</span>
                <span className="shrink-0 text-xs font-bold text-muted">{t.recipes.minutes(r.minutes)}</span>
              </span>
              {r.why && <span className="text-sm font-semibold">{r.why}</span>}
              <span className="text-xs font-bold text-muted">
                {r.allergens.length > 0 ? t.recipes.contains(r.allergens.map((a) => t.recipes.allergen[a]).join(', ')) : t.recipes.noAllergens}
              </span>
              <button type="button" aria-label={t.assistant.cook(r.title)} onClick={() => onCook(r.id)} className="h-10 rounded-field bg-plate text-sm font-extrabold text-on-plate">
                {t.recipes.choose}
              </button>
            </li>
          ))}
        </ul>
      )}
      {card.quest && <QuestIdea quest={card.quest} />}
      {card.attribution && <span className="px-1 text-[11px] font-semibold text-muted">{card.attribution}</span>}
    </div>
  )
}

function QuestIdea({ quest }: { quest: Schemas['DayQuest'] }) {
  const today = useToday()
  const take = useTakeQuests()
  // The card is a snapshot; the day knows whether the quest is still on offer
  const current = today.data?.quests.find((q) => q.id === quest.id)
  const offered = (current?.state ?? quest.state) === 'offered'
  return (
    <div className="flex flex-col gap-1.5 rounded-card bg-surface p-3.5">
      <span className="text-[15px] font-bold">{quest.title}</span>
      <span className="text-xs font-semibold text-muted">
        {t.quest.minutes(quest.duration_min)} · {t.quest.points(quest.base_points)}
      </span>
      {offered ? (
        <button
          type="button"
          aria-label={t.assistant.takeQuest(quest.title)}
          disabled={take.isPending}
          onClick={() => take.mutate([quest.id], { onSuccess: () => haptic('success') })}
          className="h-10 rounded-field bg-accent text-sm font-extrabold text-on-accent disabled:opacity-50"
        >
          {t.assistant.take}
        </button>
      ) : (
        <span className="text-sm font-bold">{t.assistant.taken}</span>
      )}
    </div>
  )
}
