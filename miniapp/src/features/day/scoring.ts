// Preview of the PRD scoring for the completion screen. Only the backend awards points.
import type { Schemas } from '../../api/client'

export const VISIBILITY_MULTIPLIER: Record<Schemas['Visibility'], number> = { friends: 1, routine: 0.75, personal: 0.5 }

export function streakMultiplier(days: number): number {
  return 1 + Math.min(3, Math.floor(days / 7)) * 0.1
}

/** Expected points; the streak grows by one with the first completion of the day. */
export function expectedPoints(base: number, visibility: Schemas['Visibility'], day: Schemas['Day']): number {
  const firstToday = !day.quests.some((q) => q.state === 'completed')
  const streak = day.streak.current_days + (firstToday ? 1 : 0)
  return Math.round(base * VISIBILITY_MULTIPLIER[visibility] * streakMultiplier(streak))
}
