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

  it('deletes a chat for me only', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const chat = db.conversations[0]!
    renderApp(`/chats/${chat.id}`)
    await user.click(await screen.findByRole('button', { name: 'Удалить чат у себя' }))
    await vi.waitFor(() => expect(chat.hiddenAt).toBeTruthy())
    await screen.findByRole('heading', { name: 'Чаты' })
    expect(screen.queryByRole('link', { name: /Лена/ })).not.toBeInTheDocument()

    db.addMessage(chat, chat.peerId, 'Ты где?', new Date(Date.parse(chat.hiddenAt!) + 1000).toISOString())
    expect(db.listConversations().find((c) => c.id === chat.id)?.last_message?.text).toBe('Ты где?')
    expect(db.messages(chat, null, 30).items.map((m) => m.text)).toEqual(['Ты где?'])
  })

  it('edits an own message', async () => {
    const user = userEvent.setup()
    const chat = db.conversations[0]!
    db.addMessage(chat, db.me.id, 'Встретимся в 7')
    renderApp(`/chats/${chat.id}`)
    await user.click(await screen.findByRole('button', { name: /Встретимся в 7/ }))
    await user.click(screen.getByRole('button', { name: 'Изменить' }))
    const input = screen.getByRole('textbox', { name: 'Сообщение' })
    expect(input).toHaveValue('Встретимся в 7')
    await user.clear(input)
    await user.type(input, 'Встретимся в 8')
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    expect(await screen.findByRole('button', { name: /Встретимся в 8.*изменено/ })).toBeInTheDocument()
    expect(chat.messages.at(-1)!.text).toBe('Встретимся в 8')
  })

  it('records and sends a voice message and a circle', async () => {
    class FakeRecorder {
      static isTypeSupported = (type: string) => ['audio/webm;codecs=opus', 'video/webm;codecs=vp8,opus'].includes(type)
      state: RecordingState = 'inactive'
      mimeType: string
      ondataavailable: ((e: { data: Blob }) => void) | null = null
      onstop: (() => void) | null = null
      constructor(
        readonly stream: MediaStream,
        options?: MediaRecorderOptions,
      ) {
        this.mimeType = options?.mimeType ?? ''
      }
      start() {
        this.state = 'recording'
      }
      stop() {
        this.state = 'inactive'
        this.ondataavailable?.({ data: new Blob(['opus'], { type: this.mimeType }) })
        this.onstop?.()
      }
    }
    const stopTrack = vi.fn()
    vi.stubGlobal('MediaRecorder', FakeRecorder)
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] }) },
    })
    const user = userEvent.setup()
    const chat = db.conversations[0]!
    renderApp(`/chats/${chat.id}`)

    // Cancelled: nothing is sent and the microphone is released
    await user.click(await screen.findByRole('button', { name: 'Записать голосовое' }))
    expect(await screen.findByRole('timer')).toHaveTextContent('Запись 0:00')
    await user.click(screen.getByRole('button', { name: 'Отменить запись' }))
    expect(stopTrack).toHaveBeenCalled()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Записать голосовое' }))
    await user.click(await screen.findByRole('button', { name: 'Отправить голосовое' }))
    expect(await screen.findByRole('button', { name: 'Слушать' })).toBeInTheDocument()
    const sent = chat.messages.at(-1)!
    expect(sent.text).toBe('')
    expect(sent.attachment?.kind).toBe('voice')

    await user.click(screen.getByRole('button', { name: 'Записать кружок' }))
    expect(await screen.findByRole('timer')).toBeInTheDocument()
    const getUserMedia = vi.mocked(navigator.mediaDevices.getUserMedia)
    expect(getUserMedia).toHaveBeenLastCalledWith(expect.objectContaining({ video: expect.objectContaining({ facingMode: 'user' }) }))
    await user.click(screen.getByRole('button', { name: 'Отправить кружок' }))
    expect(await screen.findByRole('button', { name: 'Смотреть кружок' })).toBeInTheDocument()
    expect(chat.messages.at(-1)!.attachment?.kind).toBe('video_note')
    vi.unstubAllGlobals()
    Reflect.deleteProperty(navigator, 'mediaDevices')
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
    expect(db.conversations.filter((c) => !c.coopId)).toHaveLength(2)
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
