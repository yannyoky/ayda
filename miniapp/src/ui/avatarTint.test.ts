import { initial, tintOf } from './avatarTint'

describe('letter avatars', () => {
  it('takes the whole first character, emoji included', () => {
    expect(initial('🦊 Маргарита')).toBe('🦊')
    expect(initial('ёлка')).toBe('Ё')
    expect(initial('  Jo')).toBe('J')
    expect(initial('')).toBe('?')
  })

  it('keeps one tint per user and spreads users over the palette', () => {
    expect(tintOf({ id: 'u-1', first_name: 'Лена' })).toBe(tintOf({ id: 'u-1', first_name: 'Лена' }))
    const tints = new Set(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map((id) => tintOf({ id, first_name: 'X' })))
    expect(tints.size).toBeGreaterThan(3)
    for (const tint of tints) expect(tint).toBeGreaterThanOrEqual(1)
  })
})
