import type { Schemas } from '../../api/client'
import { t } from '../../i18n'

type EventInfo = Schemas['EventInfo']

function startTime(event: EventInfo): string {
  return new Date(event.starts_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

export function eventPrice(event: EventInfo): string {
  if (event.is_free) return t.event.free
  return event.price_min ? t.event.from(event.price_min) : t.event.paid
}

/** "в 19:00 · Дом искусств · Советск · Бесплатно" (US-19: place, time, price). */
export function eventSummary(event: EventInfo): string {
  return [t.event.at(startTime(event)), event.venue ?? event.address, event.city, eventPrice(event)].filter(Boolean).join(' · ')
}
