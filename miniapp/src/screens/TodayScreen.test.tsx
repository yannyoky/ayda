import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { db } from '../mocks/db'
import { renderApp } from '../test/render'

async function checkIn(user: ReturnType<typeof userEvent.setup>, text: string, mood = 'Нормально') {
  const box = await screen.findByRole('textbox', { name: 'Какой у тебя день?' })
  if (text) await user.type(box, text)
  await user.click(screen.getByRole('radio', { name: mood }))
  await user.click(screen.getByRole('button', { name: 'Собрать квесты' }))
}

describe('Today: check-in and pool (US-05, US-06)', () => {
  it('shows streak and weekly points', async () => {
    renderApp()
    expect(await screen.findByRole('region', { name: 'Серия' })).toHaveTextContent('12дней')
    expect(screen.getByRole('region', { name: 'За неделю' })).toHaveTextContent('185')
  })

  it('submits the check-in and goes straight to the picker', async () => {
    const user = userEvent.setup()
    renderApp()
    await checkIn(user, 'дописать отчёт', 'Устал')
    expect(await screen.findByRole('heading', { name: 'Квесты на сегодня' })).toBeInTheDocument()
    expect(db.checkin).toMatchObject({ text: 'дописать отчёт', mood: 'tired' })
  })

  it('shows that it is working while the check-in is sent', async () => {
    db.reset({ onboarded: true, poolDelayMs: 0, checkinDelayMs: 300 })
    const user = userEvent.setup()
    renderApp()
    await checkIn(user, 'дописать отчёт')
    expect(await screen.findByRole('status')).toHaveTextContent('Читаю план')
    expect(screen.getByRole('button', { name: 'Собрать квесты' })).toBeDisabled()
    expect(await screen.findByRole('heading', { name: 'Квесты на сегодня' })).toBeInTheDocument()
  })

  it('waits for the pool on the picker', async () => {
    db.reset({ onboarded: true, poolDelayMs: 300 })
    const user = userEvent.setup()
    renderApp()
    await checkIn(user, '')
    expect(await screen.findByRole('status')).toHaveTextContent('Собираем квесты')
    expect((await screen.findAllByRole('button', { pressed: false }, { timeout: 3000 })).length).toBeGreaterThan(0)
  })

  it('stays on Today when quests are already taken', async () => {
    const user = userEvent.setup()
    db.submitCheckin({ text: '', mood: 'normal' })
    db.quests.slice(0, 1).forEach((q) => db.take(q))
    renderApp()
    await user.click(await screen.findByRole('button', { name: 'Изменить' }))
    await checkIn(user, 'вечером свободен')
    expect(await screen.findByText(/Чек-ин готов/)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Квесты на сегодня' })).not.toBeInTheDocument()
  })
})

describe('Quest picker (US-07, US-08)', () => {
  beforeEach(() => db.submitCheckin({ text: 'дописать отчёт', mood: 'normal' }))

  it('takes up to three quests and shows them on Today', async () => {
    const user = userEvent.setup()
    renderApp('/pick')
    const cards = await screen.findAllByRole('button', { pressed: false })
    expect(cards).toHaveLength(6)
    for (const card of cards.slice(0, 4)) await user.click(card)
    // The fourth tap is ignored: the limit is three
    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(3)
    await user.click(screen.getByRole('button', { name: /Взять 3 квеста/ }))

    const list = await screen.findByRole('region', { name: 'Квесты дня' })
    expect(within(list).getByText('Дописать отчёт')).toBeInTheDocument()
    expect(within(list).getAllByRole('button', { name: /Готово/ })).toHaveLength(3)
    expect(within(list).getByText('3 из 3')).toBeInTheDocument()
    expect(db.takenCount()).toBe(3)
  })

  it('replaces a quest with a reason and counts replacements', async () => {
    const user = userEvent.setup()
    renderApp('/pick')
    const title = db.day().quests[2]!.title
    await user.click(await screen.findByRole('button', { name: `Не сегодня: ${title}` }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Нет времени' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Замен осталось: 4')
    expect(screen.queryByText(title)).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { pressed: false })).toHaveLength(6)
  })

  it('adds an own quest that is taken right away', async () => {
    const user = userEvent.setup()
    renderApp()
    await user.click(await screen.findByRole('button', { name: 'Свой квест' }))
    const dialog = screen.getByRole('dialog', { name: 'Свой квест' })
    await user.type(within(dialog).getByRole('textbox', { name: 'Что сделаешь' }), 'Позвонить маме')
    await user.click(within(dialog).getByRole('radio', { name: 'Люди' }))
    await user.click(within(dialog).getByRole('radio', { name: '15 мин' }))
    await user.click(within(dialog).getByRole('button', { name: 'Добавить' }))
    expect(await screen.findByText('Позвонить маме')).toBeInTheDocument()
    expect(db.quests.at(-1)).toMatchObject({ source: 'custom', state: 'taken', category: 'social', base_points: 10 })
  })
})
