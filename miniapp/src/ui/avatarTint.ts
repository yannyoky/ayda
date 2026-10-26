/** Tints for letter avatars; tokens --color-avatar-1..6 differ per theme. */
const TINTS = 6

export type AvatarUser = { id?: string; first_name: string; avatar_url?: string | null }

/** First user-perceived character, so an emoji or a combined letter is never cut in half. */
export function initial(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return '?'
  const Segmenter = (Intl as { Segmenter?: typeof Intl.Segmenter }).Segmenter
  const first = Segmenter ? new Segmenter('ru', { granularity: 'grapheme' }).segment(trimmed)[Symbol.iterator]().next().value?.segment : Array.from(trimmed)[0]
  return (first ?? '?').toLocaleUpperCase('ru')
}

/** Stable tint 1..6 for a user, so each friend keeps the same colour everywhere. */
export function tintOf(user: AvatarUser): number {
  const key = user.id ?? user.first_name
  // FNV-1a spreads similar ids (uuids, short names) evenly over the palette
  let hash = 0x811c9dc5
  for (let i = 0; i < key.length; i++) hash = Math.imul(hash ^ key.charCodeAt(i), 0x01000193)
  return ((hash >>> 0) % TINTS) + 1
}

