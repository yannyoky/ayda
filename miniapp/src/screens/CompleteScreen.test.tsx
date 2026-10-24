import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { vi } from 'vitest'
import { db } from '../mocks/db'
import { server } from '../test/server'
import { renderApp } from '../test/render'

function takenWalk(): string {
  const q = db.addOwn({ title: 'Прогулка по набережной', category: 'walk', duration_min: 40 })
  db.streak = { current_days: 9, best_days: 9, freeze_available: true }
  return q.id
}

describe('Complete a quest (US-09, US-10)', () => {
  it('posts a proof with a photo and the PRD points', async () => {
    const user = userEvent.setup()
    const id = takenWalk()
    renderApp(`/quest/${id}/done`)
    const submit = await screen.findByRole('button', { name: 'Отметить' })
    // 35 × 1.0 × 1.1 on day 10 of the streak
    expect(screen.getByText('≈ +39')).toBeInTheDocument()
    expect(screen.queryByText('Рутина')).not.toBeInTheDocument()

    const photo = new File([new Uint8Array([0xff, 0xd8, 0xff])], 'walk.jpg', { type: 'image/jpeg' })
    await user.upload(screen.getByLabelText('Добавить фото'), photo)
    await user.type(screen.getByRole('textbox', { name: 'Подпись' }), 'Закат над заливом')
    await user.click(submit)

    expect(await screen.findByRole('status')).toHaveTextContent('+39')
    expect(screen.getByText('Серия: 10 дней')).toBeInTheDocument()
    expect(db.posts[0]).toMatchObject({ kind: 'proof', quest_title: 'Прогулка по набережной', caption: 'Закат над заливом' })
    expect(db.posts[0]!.photos).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'Открыть ленту' })).toBeInTheDocument()
  })

  it('posts a text-only proof to the feed', async () => {
    const user = userEvent.setup()
    const id = takenWalk()
    renderApp(`/quest/${id}/done`)
    await user.type(await screen.findByRole('textbox', { name: 'Подпись' }), 'Прошёл 5 км')
    await user.click(screen.getByRole('button', { name: 'Отметить' }))
    expect(await screen.findByRole('status')).toHaveTextContent('+39')
    expect(db.posts[0]).toMatchObject({ kind: 'proof', caption: 'Прошёл 5 км', photos: [] })
  })

  it('says when a photo could not be uploaded', async () => {
    server.use(http.put('*/mock-s3/:media_id', () => new HttpResponse(null, { status: 403 })))
    const user = userEvent.setup()
    const id = takenWalk()
    const posts = db.posts.length
    renderApp(`/quest/${id}/done`)
    const photo = new File([new Uint8Array([0xff, 0xd8, 0xff])], 'walk.jpg', { type: 'image/jpeg' })
    await user.upload(await screen.findByLabelText('Добавить фото'), photo)
    await user.click(screen.getByRole('button', { name: 'Отметить' }))
    expect(await screen.findByText(/Не получилось загрузить файл/)).toBeInTheDocument()
    expect(db.posts).toHaveLength(posts)
  })

  it('completes a personal quest without photos and without a post', async () => {
    const user = userEvent.setup()
    const id = takenWalk()
    const posts = db.posts.length
    renderApp(`/quest/${id}/done`)
    await user.click(await screen.findByText('Только я'))
    await user.click(screen.getByRole('button', { name: 'Отметить' }))
    expect(await screen.findByRole('status')).toHaveTextContent('+19')
    expect(db.posts).toHaveLength(posts)
    expect(screen.queryByRole('link', { name: 'Открыть ленту' })).not.toBeInTheDocument()
  })

  it('rejects photos that are too big or of the wrong type', async () => {
    const user = userEvent.setup({ applyAccept: false })
    const id = takenWalk()
    renderApp(`/quest/${id}/done`)
    const input = await screen.findByLabelText('Добавить фото')
    await user.upload(input, new File(['x'], 'notes.txt', { type: 'text/plain' }))
    expect(screen.getByText('Подойдут JPEG, PNG, HEIC или WebP')).toBeInTheDocument()
    const big = new File(['x'], 'big.jpg', { type: 'image/jpeg' })
    Object.defineProperty(big, 'size', { value: 11 * 1024 * 1024 })
    await user.upload(input, big)
    expect(screen.getByText('Фото больше 10 МБ')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Убрать фото 1' })).not.toBeInTheDocument()
  })

  it('posts a video proof that plays in the feed', async () => {
    const user = userEvent.setup()
    const id = takenWalk()
    renderApp(`/quest/${id}/done`)
    const video = new File([new Uint8Array([0, 0, 0, 24])], 'walk.mov', { type: 'video/quicktime' })
    await user.upload(await screen.findByLabelText('Видео'), video)
    // A video goes alone: no more photo, video or circle buttons
    expect(screen.queryByLabelText('Добавить фото')).not.toBeInTheDocument()
    expect(screen.getByText(/Хранится 30 дней/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Отметить' }))

    expect(await screen.findByRole('status')).toHaveTextContent('+39')
    expect(db.posts[0]).toMatchObject({ kind: 'proof', photos: [], video: { kind: 'video', status: 'ready' } })
    await user.click(screen.getByRole('link', { name: 'Открыть ленту' }))
    expect(await screen.findByLabelText('Видео')).toBeInTheDocument()
  })

  it('records a circle as proof', async () => {
    class FakeRecorder {
      static isTypeSupported = (type: string) => type === 'video/webm;codecs=vp8,opus'
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
        this.ondataavailable?.({ data: new Blob(['vp8'], { type: this.mimeType }) })
        this.onstop?.()
      }
    }
    const stopTrack = vi.fn()
    vi.stubGlobal('MediaRecorder', FakeRecorder)
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] }) },
    })
    try {
      const user = userEvent.setup()
      const id = takenWalk()
      renderApp(`/quest/${id}/done`)
      await user.click(await screen.findByRole('button', { name: 'Кружок' }))
      expect(await screen.findByRole('timer')).toHaveTextContent('Запись 0:00')
      await user.click(screen.getByRole('button', { name: 'Готово' }))
      expect(stopTrack).toHaveBeenCalled()
      expect(await screen.findByRole('button', { name: 'Убрать кружок' })).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Отметить' }))

      expect(await screen.findByRole('status')).toHaveTextContent('+39')
      expect(db.posts[0]).toMatchObject({ photos: [], video: { kind: 'video_note' } })
    } finally {
      vi.unstubAllGlobals()
      Reflect.deleteProperty(navigator, 'mediaDevices')
    }
  })
})
