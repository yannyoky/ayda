import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { db } from '../mocks/db'
import { renderApp } from '../test/render'

describe('Cooking quest from a recipe (M5, ADR 0014)', () => {
  beforeEach(() => db.submitCheckin({ text: 'Работа до шести', mood: 'normal' }))

  async function open(user: ReturnType<typeof userEvent.setup>) {
    renderApp('/assistant')
    await user.type(await screen.findByRole('textbox', { name: 'Спроси помощника' }), 'Что приготовить на завтрак?')
    await user.click(screen.getByRole('button', { name: 'Отправить' }))
    await user.click(await screen.findByRole('button', { name: 'Готовить: Блины на молоке' }))
    return screen.findByRole('dialog', { name: 'Готовим' })
  }

  it('is not offered on the main screen', async () => {
    renderApp('/')
    expect((await screen.findAllByText(/квест/i)).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Приготовить вместе' })).not.toBeInTheDocument()
  })

  it('cooks alone by default and adds an own quest', async () => {
    const user = userEvent.setup()
    const sheet = await open(user)
    expect(await within(sheet).findByText(/Порций: 2/)).toBeInTheDocument()
    expect(within(sheet).getByLabelText('Одному')).toBeChecked()
    expect(within(sheet).queryByRole('radiogroup', { name: 'Кто покупает продукты' })).not.toBeInTheDocument()
    await user.click(within(sheet).getByRole('button', { name: 'Добавить в квесты' }))

    expect(await screen.findByText('Готовим: Блины на молоке')).toBeInTheDocument()
    expect(db.quests.find((q) => q.title === 'Готовим: Блины на молоке')?.state).toBe('taken')
  })

  it('marks what is at home and makes a shopping and a cooking part with a friend', async () => {
    const user = userEvent.setup()
    const sheet = await open(user)
    expect(await within(sheet).findByText(/Порций: 2/)).toBeInTheDocument()
    await user.click(within(sheet).getByRole('button', { name: 'Больше порций: Блины на молоке' }))
    expect(await within(sheet).findByText('Мука пшеничная: 225')).toBeInTheDocument()
    await user.click(within(sheet).getByLabelText('Молоко: 450'))
    await user.click(within(sheet).getByLabelText('Яйца: 3'))
    await user.click(within(sheet).getByLabelText('Лена'))
    await user.click(within(sheet).getByLabelText('Друг'))
    await user.click(within(sheet).getByRole('button', { name: 'Создать план' }))

    expect(await screen.findByRole('heading', { name: 'Готовим: Блины на молоке' })).toBeInTheDocument()
    const shop = screen.getByRole('article', { name: 'Купить продукты' })
    expect(within(shop).getByText('Делает Лена')).toBeInTheDocument()
    expect(within(shop).getAllByRole('checkbox')).toHaveLength(1)
    expect(within(screen.getByRole('article', { name: 'Приготовить: Блины на молоке' })).getByText('Делаешь ты')).toBeInTheDocument()
    expect(db.coops.at(-1)!.parts).toHaveLength(2)
  })
})
