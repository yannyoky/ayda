import type { Schemas } from '../../api/client'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'

const eventWhen = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })

/** One listing from the assistant's search or the top picks; every field comes from code. */
export function EventItem({ event: e }: { event: Schemas['AssistantEvent'] }) {
  return (
    <li className="flex flex-col gap-1.5 rounded-card bg-surface p-3.5">
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
  )
}
