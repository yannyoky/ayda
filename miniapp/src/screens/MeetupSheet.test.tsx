import { fireEvent, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { db } from '../mocks/db'
import { renderApp } from '../test/render'

describe('"Айда, организуй" in a chat (M5)', () => {
  function chatWith(...texts: string[]) {
    const friend = db.friends[2]!
    db.openDirect(friend.id)
    const chat = db.conversations.find((c) => c.peerId === friend.id && !c.coopId)!
    for (const text of texts) db.addMessage(chat, friend.id, text, new Date().toISOString())
    return chat
  }

  it('shows venues with review links and makes the chosen one a plan', async () => {
    const user = userEvent.setup()
    const chat = chatWith('Го в кафе?', 'Давай вечером')
    renderApp(`/chats/${chat.id}`)
    await user.click(await screen.findByRole('button', { name: 'Айда, организуй' }))
    const sheet = await screen.findByRole('dialog', { name: 'Встреча' })
    const venues = await within(sheet).findByRole('list', { name: 'Место' })
    expect(within(venues).getAllByRole('listitem')).toHaveLength(2)
    expect(within(venues).getAllByRole('link', { name: '2ГИС' })[0]).toHaveAttribute('href', expect.stringContaining('2gis.ru'))
    expect(within(sheet).getByText('© OpenStreetMap contributors')).toBeInTheDocument()
    expect(within(sheet).getByText(/Сегодня в \d\d:\d\d/)).toBeInTheDocument()

    await user.click(within(sheet).getByRole('button', { name: 'Выбрать Кофейня на углу' }))
    expect(await screen.findByRole('heading', { name: 'Встреча: Кофейня на углу' })).toBeInTheDocument()
    expect(screen.getByText(/Сегодня в \d\d:\d\d · Кофейня на углу · Ленина, 1/)).toBeInTheDocument()
    expect(db.coops.at(-1)!.place?.name).toBe('Кофейня на углу')
  })

  it('lets the user change the proposed time before choosing a place', async () => {
    const user = userEvent.setup()
    const chat = chatWith('Го в кафе?')
    renderApp(`/chats/${chat.id}`)
    await user.click(await screen.findByRole('button', { name: 'Айда, организуй' }))
    const sheet = await screen.findByRole('dialog', { name: 'Встреча' })
    const input = await within(sheet).findByLabelText('Время')
    fireEvent.change(input, { target: { value: '23:59' } })
    expect(within(sheet).getByText('Сегодня в 23:59')).toBeInTheDocument()
    await user.click(within(sheet).getByRole('button', { name: 'Выбрать Кофейня на углу' }))
    await screen.findByRole('heading', { name: 'Встреча: Кофейня на углу' })
    const startsAt = new Date(db.coops.at(-1)!.startsAt!)
    expect([startsAt.getHours(), startsAt.getMinutes()]).toEqual([23, 59])
  })

  it('offers an online plan when the friends talk about a game', async () => {
    const user = userEvent.setup()
    const chat = chatWith('Сыграем в доту?')
    renderApp(`/chats/${chat.id}`)
    await user.click(await screen.findByRole('button', { name: 'Айда, организуй' }))
    const sheet = await screen.findByRole('dialog', { name: 'Встреча' })
    expect(await within(sheet).findByText('Онлайн: Дота')).toBeInTheDocument()
    await user.click(within(sheet).getByRole('button', { name: 'Создать план' }))
    expect(await screen.findByRole('heading', { name: 'Онлайн: Дота' })).toBeInTheDocument()
  })

  it('says so when no meetup can be read', async () => {
    const user = userEvent.setup()
    const chat = chatWith()
    renderApp(`/chats/${chat.id}`)
    await user.click(await screen.findByRole('button', { name: 'Айда, организуй' }))
    const sheet = await screen.findByRole('dialog', { name: 'Встреча' })
    expect(await within(sheet).findByText(/Не поняла, о какой встрече речь/)).toBeInTheDocument()
    expect(within(sheet).queryByRole('list', { name: 'Место' })).not.toBeInTheDocument()
  })
})
