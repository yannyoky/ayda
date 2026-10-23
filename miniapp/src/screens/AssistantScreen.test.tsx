import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ASSISTANT_DAILY_LIMIT, ASSISTANT_REPLY_CHECKIN, db } from '../mocks/db'
import { renderApp } from '../test/render'

async function ask(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(await screen.findByRole('textbox', { name: 'Спроси помощника' }), text)
  await user.click(screen.getByRole('button', { name: 'Отправить' }))
}

describe('Assistant chat (ADR 0013)', () => {
  beforeEach(() => db.submitCheckin({ text: 'Работа до шести', mood: 'normal' }))

  it('opens from the check-in and continues the day topic', async () => {
    const user = userEvent.setup()
    renderApp()
    await user.click(await screen.findByRole('link', { name: 'Чат с помощником' }))
    const chat = await screen.findByRole('list', { name: 'Помощник' })
    expect(within(chat).getByText('Работа до шести')).toBeInTheDocument()
    expect(within(chat).getByText(ASSISTANT_REPLY_CHECKIN)).toBeInTheDocument()

    await ask(user, 'Как не устать к вечеру?')
    expect(await within(chat).findByText(/начать с малого/)).toBeInTheDocument()
    expect(db.assistantMessages.filter((m) => m.role === 'user')).toHaveLength(2)
  })

  it('shows that the assistant is typing', async () => {
    db.assistantDelayMs = 300
    const user = userEvent.setup()
    renderApp('/assistant')
    await ask(user, 'Привет')
    expect(await screen.findByRole('status')).toHaveTextContent('Помощник печатает…')
    expect(await screen.findByText(/начать с малого/)).toBeInTheDocument()
    expect(screen.queryByText('Помощник печатает…')).not.toBeInTheDocument()
  })

  it('finds places for a walk with map links', async () => {
    const user = userEvent.setup()
    renderApp('/assistant')
    await user.click(await screen.findByRole('button', { name: 'Где погулять сегодня?' }))
    const park = (await screen.findByText('Центральный парк')).closest('li')!
    expect(within(park).getByText(/Парк · 1,2 км/)).toBeInTheDocument()
    expect(within(park).getByRole('link', { name: /2ГИС/ })).toHaveAttribute('href', expect.stringContaining('https://2gis.ru/search/'))
    expect(screen.getByText('© OpenStreetMap contributors')).toBeInTheDocument()
  })

  it('shows the listings found for a request', async () => {
    const user = userEvent.setup()
    renderApp('/assistant')
    await ask(user, 'Что будет в афише на выходных?')
    const jazz = (await screen.findByText('Джазовый вечер')).closest('li')!
    expect(within(jazz).getByText(/Дом искусств · Калининград · в твоём городе · от 500 ₽/)).toBeInTheDocument()
    expect(within(jazz).getByRole('link', { name: /Подробнее/ })).toHaveAttribute('href', 'https://example.com/jazz')
    const fair = screen.getByText('Ярмарка мёда').closest('li')!
    expect(within(fair).getByText(/Светлогорск · 35 км от центра · Бесплатно/)).toBeInTheDocument()
    expect(screen.getByText('Афиша: Timepad и KudaGo')).toBeInTheDocument()
  })

  it('suggests dishes and opens the cooking plan', async () => {
    const user = userEvent.setup()
    renderApp('/assistant')
    await ask(user, 'Что приготовить из курицы и риса?')
    const [first] = await screen.findAllByRole('button', { name: /^Готовить: / })
    await user.click(first!)
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })

  it('offers a new quest that can be taken', async () => {
    const user = userEvent.setup()
    renderApp('/assistant')
    await ask(user, 'Придумай квест на вечер')
    await user.click(await screen.findByRole('button', { name: 'Взять квест: Пройти 3 км по набережной' }))
    expect(await screen.findByText('Квест взят')).toBeInTheDocument()
    expect(db.quests.find((q) => q.title === 'Пройти 3 км по набережной')?.state).toBe('taken')
  })

  it('discusses a taken quest in its own topic', async () => {
    const quest = db.quests.find((q) => q.state === 'offered')!
    db.take(quest)
    const user = userEvent.setup()
    renderApp()
    await user.click(await screen.findByRole('link', { name: `Обсудить с помощником: ${quest.title}` }))
    expect(await screen.findByText(`Обсуждаем: ${quest.title}`)).toBeInTheDocument()
    expect(screen.getByText(/как разнообразить этот квест/)).toBeInTheDocument()
    await ask(user, 'Найди парк')
    expect(await screen.findByText('Центральный парк')).toBeInTheDocument()
    expect(db.assistantMessages.at(-1)?.quest_id).toBe(quest.id)
  })

  it('stops at the daily limit', async () => {
    for (let i = db.assistantThread(null).messages_left; i > 0; i--) db.sendAssistant(`Вопрос ${i}`, null)
    expect(db.assistantLeft()).toBe(0)
    expect(ASSISTANT_DAILY_LIMIT).toBe(40)
    renderApp('/assistant')
    expect(await screen.findByRole('note')).toHaveTextContent('На сегодня сообщения помощнику закончились')
    expect(screen.queryByRole('textbox', { name: 'Спроси помощника' })).not.toBeInTheDocument()
  })
})
