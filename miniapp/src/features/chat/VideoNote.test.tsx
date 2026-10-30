import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { afterTap } from './circleMode'
import { VideoNote } from './VideoNote'

const ready = { status: 'ready' as const, url: 'https://media.example/circle.mp4', duration_ms: 13_400 }

describe('VideoNote', () => {
  afterEach(() => vi.restoreAllMocks())

  it('cycles like Telegram: preview, playing, paused, playing', () => {
    expect(afterTap('preview')).toBe('playing')
    expect(afterTap('playing')).toBe('paused')
    expect(afterTap('paused')).toBe('playing')
  })

  it('loops silently, plays with sound on tap and pauses on the next tap', async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
    const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
    const user = userEvent.setup()
    const { container } = render(<VideoNote attachment={ready} onExpired={() => {}} />)
    const video = container.querySelector('video')!

    // The preview is a muted loop that starts by itself and shows the whole length
    expect(video.muted).toBe(true)
    expect(video.loop).toBe(true)
    expect(video.autoplay).toBe(true)
    expect(video.getAttribute('src')).toBe(`${ready.url}#t=0.001`)
    expect(screen.getByRole('button', { name: 'Смотреть кружок' })).toHaveTextContent('0:13')

    await user.click(screen.getByRole('button', { name: 'Смотреть кружок' }))
    expect(play).toHaveBeenCalled()
    expect(video.muted).toBe(false)
    expect(video.loop).toBe(false)
    expect(container.querySelector('svg circle')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Пауза' }))
    expect(pause).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Смотреть кружок' })).toBeInTheDocument()
  })

  it('goes back to the silent loop when it ends', async () => {
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
    const user = userEvent.setup()
    const { container } = render(<VideoNote attachment={ready} onExpired={() => {}} />)
    const video = container.querySelector('video')!
    await user.click(screen.getByRole('button', { name: 'Смотреть кружок' }))

    video.dispatchEvent(new Event('ended'))
    expect(await screen.findByRole('button', { name: 'Смотреть кружок' })).toBeInTheDocument()
    expect(video.muted).toBe(true)
    expect(video.loop).toBe(true)
    expect(container.querySelector('svg circle')).not.toBeInTheDocument()
  })
})
