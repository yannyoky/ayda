import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { db } from '../mocks/db'
import { renderApp } from '../test/render'

describe('Cooking together (M5)', () => {
  async function open(user: ReturnType<typeof userEvent.setup>) {
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: 'Приготовить вместе' }))
    return screen.findByRole('dialog', { name: 'Готовим вместе' })
  }

  it('drops recipes with a named allergen and shows what is left', async () => {
    const user = userEvent.setup()
    const sheet = await open(user)
    await user.click(within(sheet).getByLabelText('яйца'))
    await user.click(within(sheet).getByRole('button', { name: 'Подобрать' }))
    const list = await within(sheet).findByRole('list', { name: 'Готовим вместе' })
    expect(within(list).getAllByRole('listitem').map((li) => within(li).getByText(/салат|Блины|карбонара/).textContent)).toEqual(['Греческий салат'])
    expect(within(sheet).getByText(/Рецепты с названными аллергенами убраны/)).toBeInTheDocument()
  })

  it('picks a recipe, marks what is at home and makes a shopping and a cooking part', async () => {
    const user = userEvent.setup()
    const sheet = await open(user)
    await user.click(within(sheet).getByLabelText('Завтрак'))
    await user.click(within(sheet).getByRole('button', { name: 'Подобрать' }))
    const card = await within(sheet).findByRole('listitem')
    expect(within(card).getByText('Блины на молоке')).toBeInTheDocument()
    expect(within(card).getByText('Содержит: яйца, глютен, молоко')).toBeInTheDocument()
    await user.click(within(card).getByRole('button', { name: 'Выбрать «Блины на молоке»' }))

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
