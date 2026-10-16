import { basePoints, MockDb, streakMultiplier } from './db'

describe('mock scoring follows the PRD', () => {
  it('maps duration to base points', () => {
    expect([10, 15, 16, 30, 31, 60, 61].map(basePoints)).toEqual([10, 10, 20, 20, 35, 35, 50])
  })

  it('caps the streak bonus at +30%', () => {
    expect([0, 6, 7, 14, 21, 70].map(streakMultiplier)).toEqual([1, 1, 1.1, 1.2, 1.3, 1.3])
  })

  it('awards 39 points for a 40-minute walk with a photo on day 10 of a streak', () => {
    const db = new MockDb({ onboarded: true, poolDelayMs: 0 })
    db.streak = { current_days: 9, best_days: 9, freeze_available: true }
    const walk = db.addOwn({ title: 'Прогулка', category: 'walk', duration_min: 40 })
    const result = db.complete(db.quest(walk.id)!, { visibility: 'friends', media_ids: ['00000000-0000-4000-8000-000000000001'] })
    expect(result.points_awarded).toBe(39)
    expect(result.streak.current_days).toBe(10)
    expect(result.post_id).not.toBeNull()
  })
})

describe('mock pool', () => {
  it('builds 6 quests with check-in tasks first and a rest quest when tired', () => {
    const db = new MockDb({ onboarded: true, poolDelayMs: 0 })
    db.submitCheckin({ text: 'дописать отчёт\nкупить подарок', mood: 'tired' })
    const day = db.day()
    expect(day.pool_status).toBe('ready')
    expect(day.quests).toHaveLength(6)
    expect(day.quests.slice(0, 2).map((q) => q.source)).toEqual(['checkin_task', 'checkin_task'])
    expect(day.quests.some((q) => q.category === 'rest')).toBe(true)
  })

  it('keeps taken quests on a repeated check-in', () => {
    const db = new MockDb({ onboarded: true, poolDelayMs: 0 })
    db.submitCheckin({ text: '', mood: 'normal' })
    const first = db.day().quests[0]!
    db.take(db.quest(first.id)!)
    db.submitCheckin({ text: '', mood: 'energetic' })
    const quests = db.day().quests
    expect(quests.find((q) => q.id === first.id)?.state).toBe('taken')
    expect(quests).toHaveLength(6)
  })
})
