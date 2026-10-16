import { QueryClient } from '@tanstack/react-query'
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import type { Schemas } from '../api/client'
import { messagesKey, type MessagePages } from '../api/queries'
import { launchPath } from '../app/launch'
import { db } from '../mocks/db'
import { handleRealtimeEvent } from '../realtime/realtime'
import { renderApp } from '../test/render'
import { fakeTelegram } from '../test/telegram'

describe('Chats (US-17)', () => {
  it('lists chats with unread counts and a badge on the tab', async () => {
    renderApp('/chats')
    const list = await screen.findByRole('list', { name: 'Чаты' })
    const lena = within(list).getByRole('link', { name: /Лена/ })
    expect(lena).toHaveTextContent('Договорились 🙌')
    expect(within(lena).getByLabelText('непрочитанных: 1')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Чаты, непрочитанных: 1' })).toBeInTheDocument()
  })

  it('opens a chat, marks it read and sends a message', async () => {
    const user = userEvent.setup()
    renderApp('/chats')
    await user.click(await screen.findByRole('link', { name: /Лена/ }))

    const history = await screen.findByRole('list', { name: 'Лена' })
    expect(await within(history).findByText('Привет! Завтра бегаем?')).toBeInTheDocument()
    expect(within(history).getByText('Давай, в 8 у парка')).toBeInTheDocument()
    const chat = db.conversations[0]!
    await vi.waitFor(() => expect(chat.lastRead).toBe(chat.messages.at(-1)!.id))

    await user.type(screen.getByRole('textbox', { name: 'Сообщение' }), 'До завтра!')
    await user.click(screen.getByRole('button', { name: 'Отправить' }))
    expect(await within(history).findByText('До завтра!')).toBeInTheDocument()
    const sent = chat.messages.at(-1)!
    expect(sent.text).toBe('До завтра!')
    expect(sent.client_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(screen.getByRole('textbox', { name: 'Сообщение' })).toHaveValue('')
  })

  it('deletes an own message', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderApp(`/chats/${db.conversations[0]!.id}`)
    await user.click(await screen.findByRole('button', { name: /Давай, в 8 у парка/ }))
    await user.click(screen.getByRole('button', { name: 'Удалить сообщение' }))
    await vi.waitFor(() => expect(screen.queryByText('Давай, в 8 у парка')).not.toBeInTheDocument())
    expect(db.conversations[0]!.messages.map((m) => m.text)).not.toContain('Давай, в 8 у парка')
    vi.restoreAllMocks()
  })

  it('starts a chat with a friend from the friends list', async () => {
    const user = userEvent.setup()
    renderApp('/friends')
    await user.click(await screen.findByRole('button', { name: 'Написать Дима' }))
    expect(await screen.findByRole('heading', { name: 'Дима' })).toBeInTheDocument()
    expect(await screen.findByText('Сообщений пока нет')).toBeInTheDocument()
    expect(db.conversations).toHaveLength(2)
  })

  it('keeps the history readable once the friendship is removed', async () => {
    const chat = db.conversations[0]!
    db.friends = db.friends.filter((f) => f.id !== chat.peerId)
    renderApp(`/chats/${chat.id}`)
    expect(await screen.findByRole('note')).toHaveTextContent('чат открыт только для чтения')
    expect(await screen.findByText('Привет! Завтра бегаем?')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Сообщение' })).not.toBeInTheDocument()
  })

  it('opens the chat from a bot notice link without treating it as an invite', async () => {
    const chat = db.conversations[0]!
    const param = `c${chat.id.replaceAll('-', '')}`
    expect(launchPath(param)).toBe(`/chats/${chat.id}`)
    expect(launchPath('r-morning')).toBe('/')
    expect(launchPath('k3J9xQ2mLp')).toBe('/')

    fakeTelegram('query_id=AAE&user=%7B%7D&hash=abc', param)
    renderApp(launchPath(param))
    expect(await screen.findByRole('heading', { name: 'Лена' })).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('Realtime events (ADR 0007)', () => {
  const author = { id: 'u1', first_name: 'Лена', avatar_url: null }
  const message = (id: number, client_id: string | null = null): Schemas['Message'] => ({
    id,
    conversation_id: 'c1',
    author,
    text: `m${id}`,
    created_at: new Date().toISOString(),
    client_id,
  })

  function cached(client: QueryClient) {
    return client.getQueryData<MessagePages>(messagesKey('c1'))!.pages.flatMap((p) => p.items.map((m) => m.id))
  }

  it('adds new messages once and ignores unknown events', () => {
    const client = new QueryClient()
    client.setQueryData<MessagePages>(messagesKey('c1'), { pages: [{ items: [message(1)], next_cursor: null }], pageParams: [null] })

    handleRealtimeEvent(client, { type: 'message.created', conversation_id: 'c1', message: message(2, 'x') })
    handleRealtimeEvent(client, { type: 'message.created', conversation_id: 'c1', message: message(2, 'x') })
    handleRealtimeEvent(client, { type: 'coop.something_new' })
    expect(cached(client)).toEqual([2, 1])

    handleRealtimeEvent(client, { type: 'message.deleted', conversation_id: 'c1', message_id: 1 })
    expect(cached(client)).toEqual([2])
  })
})
