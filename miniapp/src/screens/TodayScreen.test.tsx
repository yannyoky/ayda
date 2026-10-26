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
  it('shows the date, the city and no greeting or stats', async () => {
    renderApp()
    expect(await screen.findByText(/· Калининград ·/)).toBeInTheDocument()
    expect(screen.queryByText(/Привет/)).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Серия' })).not.toBeInTheDocument()
  })

  it('shows the top events nearby', async () => {
    renderApp()
    const top = await screen.findByRole('region', { name: 'Топ рядом' })
    const fort = within(top).getByText('Реконструкция боя за форт № 5').closest('li')!
    expect(within(fort).getByText(/Форт № 5 · Калининград · в твоём городе · Бесплатно/)).toBeInTheDocument()
    expect(within(fort).getByRole('link', { name: /Подробнее/ })).toHaveAttribute('href', 'https://example.com/fort')
    expect(within(top).getByText(/35 км от центра · от 300 ₽/)).toBeInTheDocument()
  })

  it('submits the check-in and goes straight to the picker', async () => {
    const user = userEvent.setup()
    renderApp()
    await checkIn(user, 'дописать отчёт', 'Без сил')
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

  it('takes more than three quests and shows them on Today', async () => {
    const user = userEvent.setup()
    renderApp('/pick')
    expect(await screen.findByText(/бери сколько хочешь, очки за первые 5/)).toBeInTheDocument()
    const cards = await screen.findAllByRole('button', { pressed: false })
    expect(cards).toHaveLength(6)
    for (const card of cards.slice(0, 5)) await user.click(card)
    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(5)
    await user.click(screen.getByRole('button', { name: /Взять 5 квестов/ }))

    const list = await screen.findByRole('region', { name: 'Квесты дня' })
    expect(within(list).getByText('Дописать отчёт')).toBeInTheDocument()
    expect(within(list).getAllByRole('button', { name: /Готово/ })).toHaveLength(5)
    expect(within(list).getByText('с очками 0 из 5')).toBeInTheDocument()
    expect(db.takenCount()).toBe(5)
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

describe('Today as one card (design pass)', () => {
  it('names the next step in the title', async () => {
    renderApp()
    expect(await screen.findByRole('heading', { level: 1, name: 'Начнём день' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Квесты дня' })).not.toBeInTheDocument()
  })

  it('counts done quests and keeps only "Готово" in the row', async () => {
    const user = userEvent.setup()
    db.submitCheckin({ text: '', mood: 'normal' })
    const quest = db.quests[0]!
    db.take(quest)
    db.take(db.quests[1]!)
    renderApp()
    expect(await screen.findByRole('heading', { level: 1, name: 'Сделано 0 из 2' })).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Сделано за день' })).toHaveAttribute('aria-valuemax', '2')
    const row = screen.getByRole('button', { name: new RegExp(`^${quest.title}`) }).closest('li')!
    expect(within(row).getAllByRole('button')).toHaveLength(2)

    await user.click(within(row).getByRole('button', { name: new RegExp(`^${quest.title}`) }))
    const sheet = screen.getByRole('dialog', { name: quest.title })
    expect(within(sheet).getByRole('link', { name: `Обсудить с помощником: ${quest.title}` })).toBeInTheDocument()
    expect(within(sheet).getByRole('button', { name: `Позвать друзей на «${quest.title}»` })).toBeInTheDocument()
    await user.click(within(sheet).getByRole('button', { name: 'Готово, отметить' }))
    expect(await screen.findByRole('button', { name: 'Отметить' })).toBeInTheDocument()
  })
})
