import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import type { Schemas } from '../../api/client'
import { usePickMeetup, useSuggestMeetup } from '../../api/queries'
import { t } from '../../i18n'
import { haptic } from '../../telegram/webapp'
import { Sheet } from '../../ui/Sheet'

const timeFormat = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' })

/** "Айда, организуй": the assistant read the last messages on this tap; code found the places. */
export function MeetupSheet({ conversationId, onClose }: { conversationId: string; onClose: () => void }) {
  const navigate = useNavigate()
  const suggest = useSuggestMeetup(conversationId)
  const pick = usePickMeetup(conversationId)
  const { mutate: load } = suggest

  useEffect(() => {
    load()
  }, [load])

  const offer = suggest.data
  const time = offer?.starts_at ? timeFormat.format(new Date(offer.starts_at)) : null

  function choose(body: Omit<Schemas['MeetupPick'], 'starts_at'>) {
    if (!offer?.starts_at) return
    pick.mutate(
      { ...body, starts_at: offer.starts_at },
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
    <Sheet title={t.meetup.title} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {suggest.isPending && (
          <p role="status" className="m-0 text-sm font-bold text-muted">
            {t.meetup.reading}
          </p>
        )}
        {suggest.isError && (
          <div className="flex flex-col gap-2">
            <p role="alert" className="m-0 text-sm font-bold">
              {t.meetup.failed}
            </p>
            <button type="button" onClick={() => load()} className="h-11 self-start rounded-field bg-surface px-4 text-sm font-extrabold">
              {t.meetup.retry}
            </button>
          </div>
        )}
        {offer?.note && <p className="m-0 rounded-card bg-surface p-4 text-sm font-bold">{offer.note}</p>}
        {offer && time && offer.kind !== 'unclear' && <p className="m-0 font-display text-base font-bold">{t.meetup.when(time)}</p>}

        {offer?.kind === 'online' && offer.activity && (
          <div className="flex flex-col gap-3 rounded-card bg-surface p-4">
            <span className="text-[15px] font-extrabold">{t.meetup.online(offer.activity)}</span>
            <button
              type="button"
              disabled={pick.isPending}
              onClick={() => choose({ activity: offer.activity })}
              className="h-12 rounded-[16px] bg-plate text-sm font-extrabold text-on-plate disabled:opacity-50"
            >
              {t.meetup.createOnline}
            </button>
          </div>
        )}

        {offer && offer.venues.length > 0 && (
          <ul aria-label={t.meetup.place} className="m-0 flex list-none flex-col gap-2 p-0">
            {offer.venues.map((v) => (
              <li key={v.id} className="flex flex-col gap-2 rounded-card bg-surface p-4">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-display text-[15px] font-bold">{v.name}</span>
                  <span className="shrink-0 text-xs font-bold text-muted">{t.meetup.kinds[v.kind]}</span>
                </div>
                <p className="m-0 text-sm font-semibold text-muted">
                  {[v.address, t.meetup.distance(v.distance_m), v.open_now === null ? null : v.open_now ? t.meetup.open : t.meetup.closed].filter(Boolean).join(' · ')}
                </p>
                <p className="m-0 flex flex-wrap gap-x-3 text-sm font-bold">
                  <span className="text-muted">{t.meetup.reviews}:</span>
                  <a href={v.gis_url} target="_blank" rel="noreferrer">
                    {t.meetup.gis}
                  </a>
                  <a href={v.yandex_url} target="_blank" rel="noreferrer">
                    {t.meetup.yandex}
                  </a>
                </p>
                <button
                  type="button"
                  aria-label={t.meetup.choose(v.name)}
                  disabled={pick.isPending}
                  onClick={() => choose({ venue_id: v.id })}
                  className="h-12 rounded-[16px] bg-plate text-sm font-extrabold text-on-plate disabled:opacity-50"
                >
                  {t.chats.choose}
                </button>
              </li>
            ))}
          </ul>
        )}
        {offer?.attribution && <p className="m-0 text-xs font-semibold text-muted">{offer.attribution}</p>}
        {pick.isError && (
          <p role="alert" className="m-0 text-sm font-bold">
            {t.meetup.failed}
          </p>
        )}
        <p className="m-0 text-xs font-semibold text-muted">{t.meetup.hint}</p>
      </div>
    </Sheet>
  )
}
