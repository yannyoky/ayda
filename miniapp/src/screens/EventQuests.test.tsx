import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { db } from '../mocks/db'
import { renderApp } from '../test/render'

function eventQuest() {
  const quest = db.day().quests.find((q) => q.source === 'event')
  if (!quest?.event) throw new Error('no event quest in the mock pool')
  return quest as typeof quest & { event: NonNullable<typeof quest.event> }
}

function time(iso: string) {
  return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

describe('Event quests (US-19)', () => {
  beforeEach(() => db.submitCheckin({ text: '', mood: 'normal' }))

  it('shows time, place and price in the picker and opens the source page', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    const user = userEvent.setup()
    const quest = eventQuest()
    renderApp('/pick')

    const card = (await screen.findByText(quest.title)).closest('li')!
    expect(card).toHaveTextContent(`в ${time(quest.event.starts_at)} · Музей Мирового океана · Бесплатно`)
    await user.click(within(card).getByRole('button', { name: `${quest.title}: подробнее на Timepad` }))
    expect(open).toHaveBeenCalledWith(quest.event.url, '_blank', 'noopener')
    open.mockRestore()
  })

  it('keeps the event details on Today once taken', async () => {
    const user = userEvent.setup()
    const quest = eventQuest()
    renderApp('/pick')
    await user.click(await screen.findByRole('button', { name: new RegExp(quest.title) , pressed: false }))
    await user.click(screen.getByRole('button', { name: /Взять 1 квест/ }))

    const list = await screen.findByRole('region', { name: 'Квесты дня' })
    const row = within(list).getByText(quest.title).closest('li')!
    expect(row).toHaveTextContent(`в ${time(quest.event.starts_at)} · Музей Мирового океана · Бесплатно`)
    await user.click(within(row).getByRole('button', { name: new RegExp(`^${quest.title.replace(/[«»]/g, '.')}`) }))
    expect(within(screen.getByRole('dialog')).getByRole('button', { name: `${quest.title}: подробнее на Timepad` })).toBeInTheDocument()
  })

  it('names another city of the region and the lowest price', async () => {
    const stored = db.quest(eventQuest().id)!
    stored.event = { ...stored.event!, venue: 'Дом искусств', city: 'Зеленоградск', is_free: false, price_min: 1500 }
    renderApp('/pick')
    const card = (await screen.findByText(stored.title)).closest('li')!
    expect(card).toHaveTextContent(/Дом искусств · Зеленоградск · от 1\s500 ₽/)
  })
})
