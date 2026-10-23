import { useTopEvents } from '../../api/queries'
import { t } from '../../i18n'
import { EventItem } from './EventItem'

/** "Top nearby" (ADR 0016): the region's most notable events, whatever the user's tastes. */
export function TopEventsCard() {
  const top = useTopEvents()
  const items = top.data?.items ?? []
  if (items.length === 0) return null
  return (
    <section aria-labelledby="top-events-title" className="flex flex-col gap-2.5 rounded-card bg-surface p-4">
      <h2 id="top-events-title" className="m-0 font-display text-base font-bold">
        {t.today.topEvents}
      </h2>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {items.map((e) => (
          <EventItem key={e.id} event={e} />
        ))}
      </ul>
      <span className="px-1 text-[11px] font-semibold text-muted">{top.data?.attribution}</span>
    </section>
  )
}
