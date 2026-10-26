import { QueryClient } from '@tanstack/react-query'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { coopKey } from '../api/queries'
import { launchPath } from '../app/launch'
import { db, MAX_TAKEN } from '../mocks/db'
import { handleRealtimeEvent } from '../realtime/realtime'
import { renderApp } from '../test/render'

const WALK = 'Прогулка на 10 000 шагов'

describe('Co-op quests (US-18)', () => {
  it('accepts an invitation on Today and gets the bonus for finishing last', async () => {
    const user = userEvent.setup()
    renderApp('/')
    const invites = await screen.findByRole('region', {
      name: 'Тебя зовут вместе',
    })
    expect(within(invites).getByText('Дима зовёт')).toBeInTheDocument()
    await user.click(within(invites).getByRole('button', { name: 'Принять' }))

    // The quest joins the day, marked as a co-op, and the invitation is gone
    await user.click(await screen.findByRole('button', { name: new RegExp(`^${WALK}`) }))
    expect(within(screen.getByRole('dialog')).getByRole('link', { name: `Совместный квест «${WALK}»` })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await vi.waitFor(() => expect(screen.queryByRole('region', { name: 'Тебя зовут вместе' })).not.toBeInTheDocument())
    expect(screen.getByText(/Вместе · 60 мин/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: `Готово: ${WALK}` }))
    await user.click(await screen.findByText('Только я'))
    await user.click(screen.getByRole('button', { name: 'Отметить' }))
    expect(await screen.findByText(/за совместный квест: все справились/)).toBeInTheDocument()
    expect(db.coops[0]!.participants.every((p) => p.completed)).toBe(true)
  })

  it('invites friends to a taken quest and shows who is in', async () => {
    const user = userEvent.setup()
    const quest = db.addOwn({
      title: 'Час английского',
      category: 'learning',
      duration_min: 60,
    })
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: /^Час английского/ }))
    await user.click(screen.getByRole('button', { name: 'Позвать друзей на «Час английского»' }))
    const sheet = await screen.findByRole('dialog', { name: 'Сделать вместе' })
    await user.click(await within(sheet).findByText('Лена'))
    await user.click(within(sheet).getByText('Дима'))
    await user.click(within(sheet).getByRole('button', { name: 'Позвать (2)' }))

    expect(await screen.findByRole('heading', { name: 'Час английского' })).toBeInTheDocument()
    const people = screen.getByRole('region', { name: 'Участники' })
    expect(within(people).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['ССаша (ты)зовёт', 'ЛЛенаещё думает', 'ДДимаещё думает'])
    expect(screen.getByText('Если справятся все, кто принял, каждому +50% очков')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Открыть чат' })).toBeInTheDocument()
    expect(db.quests.find((q) => q.id === quest.id)?.coop_id).toBe(db.coops.at(-1)!.id)
  })

  it('opens from the bot link and declines', async () => {
    const user = userEvent.setup()
    const coop = db.coops[0]!
    const path = launchPath(`q${coop.id.replaceAll('-', '')}`)
    expect(path).toBe(`/coops/${coop.id}`)
    renderApp(path)
    expect(await screen.findByRole('heading', { name: WALK })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Открыть чат' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Не сейчас' }))
    expect(await screen.findByText('Ты отказался от этого квеста')).toBeInTheDocument()
  })

  it('shows the abuse guard when accepting', async () => {
    const user = userEvent.setup()
    for (let i = 0; i < MAX_TAKEN; i++) db.addOwn({ title: `Квест ${i + 1}`, category: 'project', duration_min: 30 })
    renderApp(`/coops/${db.coops[0]!.id}`)
    await user.click(await screen.findByRole('button', { name: 'Принять' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('На сегодня взято слишком много квестов')
  })

  it('reloads a co-op on a realtime update', () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    handleRealtimeEvent(client, { type: 'coop.updated', coop_id: 'c1' })
    expect(spy).toHaveBeenCalledWith({ queryKey: coopKey('c1') })
  })
})

describe('Shared plans: parts and hand-offs (M5)', () => {
  const lena = () => db.friends[0]!
  const me = () => db.me

  function cooking() {
    return db.addPlan(
      'Готовим: Блины',
      [lena().id],
      [
        {
          title: 'Купить продукты',
          assigneeId: me().id,
          items: ['Мука: 150 г', 'Молоко: 300 мл'],
        },
        {
          title: 'Приготовить блины',
          assigneeId: lena().id,
          items: ['Взбить яйца с молоком.'],
          opensAfter: 0,
        },
      ],
    )
  }

  it('shows the parts with their assignee and state, and ticks the open list', async () => {
    const user = userEvent.setup()
    const coop = cooking()
    renderApp(`/coops/${coop.id}`)
    const shop = await screen.findByRole('article', {
      name: 'Купить продукты',
    })
    expect(within(shop).getByText('Делаешь ты')).toBeInTheDocument()
    expect(within(shop).getByText('сейчас')).toBeInTheDocument()
    const cook = screen.getByRole('article', { name: 'Приготовить блины' })
    expect(within(cook).getByText('Делает Лена')).toBeInTheDocument()
    expect(within(cook).getByText('ждёт своей очереди')).toBeInTheDocument()
    expect(within(cook).getByRole('checkbox')).toBeDisabled()

    await user.click(within(shop).getByRole('checkbox', { name: 'Мука: 150 г' }))
    await vi.waitFor(() =>
      expect(within(screen.getByRole('article', { name: 'Купить продукты' })).getByRole('checkbox', { name: 'Мука: 150 г' })).toBeChecked(),
    )
    expect(coop.parts![0]!.items[0]!.done).toBe(true)
  })

  it('offers a part to a friend and withdraws the offer', async () => {
    const user = userEvent.setup()
    const coop = cooking()
    renderApp(`/coops/${coop.id}`)
    const shop = await screen.findByRole('article', {
      name: 'Купить продукты',
    })
    await user.click(within(shop).getByRole('button', { name: 'Передать другу' }))
    await user.click(within(shop).getByRole('button', { name: 'Передать Лена' }))
    expect(await within(shop).findByText('Предложено Лена, ждём ответа')).toBeInTheDocument()
    expect(coop.parts![0]!.handoffToId).toBe(lena().id)

    await user.click(within(shop).getByRole('button', { name: 'Отозвать' }))
    expect(await within(shop).findByRole('button', { name: 'Передать другу' })).toBeInTheDocument()
    expect(coop.parts![0]!.handoffToId).toBeNull()
  })

  it('takes over a part handed to me and finishes it, which opens the next one', async () => {
    const user = userEvent.setup()
    const coop = cooking()
    coop.parts![0]!.assigneeId = lena().id
    coop.parts![0]!.handoffToId = me().id
    renderApp(`/coops/${coop.id}`)
    const shop = await screen.findByRole('article', {
      name: 'Купить продукты',
    })
    expect(within(shop).getByText('Лена передаёт тебе эту часть')).toBeInTheDocument()
    await user.click(within(shop).getByRole('button', { name: 'Взять часть' }))
    expect(await within(shop).findByText('Делаешь ты')).toBeInTheDocument()
    await user.click(within(shop).getByRole('button', { name: 'Отметить часть' }))
    await user.click(await screen.findByText('Только я'))
    await user.click(screen.getByRole('button', { name: 'Отметить' }))
    await screen.findByRole('link', { name: 'На главную' })
    expect(coop.parts![0]!.state).toBe('done')
    expect(coop.parts![1]!.state).toBe('open')
  })

  it('declines a part handed to me', async () => {
    const user = userEvent.setup()
    const coop = cooking()
    coop.parts![0]!.assigneeId = lena().id
    coop.parts![0]!.handoffToId = me().id
    renderApp(`/coops/${coop.id}`)
    const shop = await screen.findByRole('article', {
      name: 'Купить продукты',
    })
    await user.click(within(shop).getByRole('button', { name: 'Не буду' }))
    await vi.waitFor(() =>
      expect(within(screen.getByRole('article', { name: 'Купить продукты' })).queryByRole('button', { name: 'Взять часть' })).not.toBeInTheDocument(),
    )
    expect(coop.parts![0]!.assigneeId).toBe(lena().id)
  })
})
