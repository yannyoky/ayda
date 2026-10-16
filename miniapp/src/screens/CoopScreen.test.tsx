import { QueryClient } from '@tanstack/react-query'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { coopKey } from '../api/queries'
import { launchPath } from '../app/launch'
import { db } from '../mocks/db'
import { handleRealtimeEvent } from '../realtime/realtime'
import { renderApp } from '../test/render'

const WALK = 'Прогулка на 10 000 шагов'

describe('Co-op quests (US-18)', () => {
  it('accepts an invitation on Today and gets the bonus for finishing last', async () => {
    const user = userEvent.setup()
    renderApp('/')
    const invites = await screen.findByRole('region', { name: 'Тебя зовут вместе' })
    expect(within(invites).getByText('Дима зовёт')).toBeInTheDocument()
    await user.click(within(invites).getByRole('button', { name: 'Принять' }))

    // The quest joins the day, marked as a co-op, and the invitation is gone
    expect(await screen.findByRole('link', { name: `Совместный квест «${WALK}»` })).toBeInTheDocument()
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
    const quest = db.addOwn({ title: 'Час английского', category: 'learning', duration_min: 60 })
    renderApp('/')
    await user.click(await screen.findByRole('button', { name: 'Позвать друзей на «Час английского»' }))
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

  it('shows the daily limit when accepting', async () => {
    const user = userEvent.setup()
    for (const title of ['Один', 'Два', 'Три']) db.addOwn({ title, category: 'project', duration_min: 30 })
    renderApp(`/coops/${db.coops[0]!.id}`)
    await user.click(await screen.findByRole('button', { name: 'Принять' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Сегодня уже взято 3 квеста')
  })

  it('reloads a co-op on a realtime update', () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, 'invalidateQueries')
    handleRealtimeEvent(client, { type: 'coop.updated', coop_id: 'c1' })
    expect(spy).toHaveBeenCalledWith({ queryKey: coopKey('c1') })
  })
})
