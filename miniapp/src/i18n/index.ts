import { ru } from './ru'

// One locale for the MVP; the indirection keeps call sites unchanged when more arrive
export const t = ru

const weekdayDate = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })
const shortDay = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' })
const integer = new Intl.NumberFormat('ru-RU')

export function formatDayTitle(date: Date): string {
  const s = weekdayDate.format(date)
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** "Пн, 26 октября": the quiet date line above a screen title. */
export function formatShortDay(date: Date): string {
  const s = shortDay.format(date)
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function formatNumber(n: number): string {
  return integer.format(n)
}

/** Russian plural form: plural(5, ['день', 'дня', 'дней']) → 'дней'. */
export function plural(n: number, forms: readonly [string, string, string]): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1]
  return forms[2]
}

const relative = new Intl.RelativeTimeFormat('ru-RU', { numeric: 'auto' })
const shortDate = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' })

/** '20 минут назад', 'вчера', or a date for anything older than a week. */
export function formatAgo(iso: string, now = Date.now()): string {
  const diff = (Date.parse(iso) - now) / 1000
  const abs = Math.abs(diff)
  if (abs < 60) return ru.time.justNow
  if (abs < 3600) return relative.format(Math.round(diff / 60), 'minute')
  if (abs < 86_400) return relative.format(Math.round(diff / 3600), 'hour')
  if (abs < 7 * 86_400) return relative.format(Math.round(diff / 86_400), 'day')
  return shortDate.format(new Date(iso))
}
