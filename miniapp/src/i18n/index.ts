import { ru } from './ru'

// One locale for the MVP; the indirection keeps call sites unchanged when more arrive
export const t = ru

const weekdayDate = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })
const integer = new Intl.NumberFormat('ru-RU')

export function formatDayTitle(date: Date): string {
  const s = weekdayDate.format(date)
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
