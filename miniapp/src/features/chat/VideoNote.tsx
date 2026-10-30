import { useEffect, useRef, useState } from 'react'
import type { Schemas } from '../../api/client'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'
import { afterTap, type CircleMode } from './circleMode'
import { formatSeconds } from './useRecorder'

interface Props {
  /** A chat attachment or a feed post's circle. */
  attachment: Pick<Schemas['Attachment'], 'status' | 'url' | 'duration_ms'>
  /** The play link is short-lived: ask for fresh messages when it stops working. */
  onExpired: () => void
}

/** Circles loop without sound on their own unless the browser asks to save data. */
function mutedAutoplayAllowed(): boolean {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection
  return connection?.saveData !== true
}

/** Only one circle plays with sound at a time: starting another one returns the first to preview. */
let sounding: { stop: () => void } | null = null

const RING = 2 * Math.PI * 48

function play(el: HTMLVideoElement): Promise<void> {
  try {
    return Promise.resolve(el.play())
  } catch (e) {
    return Promise.reject(e)
  }
}

/**
 * A circle ("кружок") that behaves like in Telegram: it loops without sound, a tap plays it from
 * the start with sound and a progress ring along the edge, another tap pauses, and when it ends it
 * goes back to the silent loop.
 */
export function VideoNote({ attachment, onExpired }: Props) {
  const video = useRef<HTMLVideoElement | null>(null)
  const claim = useRef({ stop: () => {} })
  const [autoplay] = useState(mutedAutoplayAllowed)
  const [mode, setMode] = useState<CircleMode>('preview')
  const [position, setPosition] = useState(0)
  const [length, setLength] = useState((attachment.duration_ms ?? 0) / 1000)

  useEffect(() => () => video.current?.pause(), [])
  useEffect(() => {
    const own = claim.current
    return () => {
      if (sounding === own) sounding = null
    }
  }, [])

  if (attachment.status !== 'ready' || !attachment.url) {
    const text = attachment.status === 'expired' ? t.chats.circleExpired : attachment.status === 'failed' ? t.chats.circleFailed : t.chats.circleProcessing
    return (
      <span className="flex size-[200px] items-center justify-center rounded-full bg-surface p-6 text-center text-sm font-bold text-muted">{text}</span>
    )
  }

  function toPreview() {
    const el = video.current
    if (sounding === claim.current) sounding = null
    setMode('preview')
    setPosition(0)
    if (!el) return
    el.muted = true
    el.loop = true
    el.currentTime = 0
    if (autoplay) void play(el).catch(() => {})
    else el.pause()
  }

  function takeSound() {
    claim.current.stop = toPreview
    if (sounding !== claim.current) {
      const previous = sounding
      sounding = claim.current
      previous?.stop()
    }
  }

  function toggle() {
    const el = video.current
    if (!el) return
    if (mode === 'playing') {
      el.pause()
    } else {
      takeSound()
      if (mode === 'preview') {
        el.muted = false
        el.loop = false
        el.currentTime = 0
        setPosition(0)
      }
      void play(el).catch(() => toPreview())
    }
    setMode(afterTap(mode))
  }

  const active = mode !== 'preview'
  const progress = length > 0 ? Math.min(position / length, 1) : 0
  const left = active ? length - position : length
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={mode === 'playing' ? t.chats.circlePause : t.chats.circlePlay}
      className={`relative block shrink-0 overflow-hidden rounded-full bg-surface p-0 transition-[width,height] duration-200 ease-out ${active ? 'size-[240px]' : 'size-[200px]'}`}
    >
      <video
        ref={video}
        // #t= makes browsers that skip autoplay still draw the first frame instead of an empty circle.
        src={`${attachment.url}#t=0.001`}
        preload={autoplay ? 'auto' : 'metadata'}
        autoPlay={autoplay}
        muted
        loop
        playsInline
        className="size-full object-cover"
        onLoadedMetadata={(e) => {
          if (Number.isFinite(e.currentTarget.duration) && e.currentTarget.duration > 0) setLength(e.currentTarget.duration)
        }}
        onEnded={toPreview}
        onTimeUpdate={(e) => {
          if (mode !== 'preview') setPosition(e.currentTarget.currentTime)
        }}
        onError={onExpired}
      />
      {active && (
        <svg viewBox="0 0 100 100" aria-hidden className="pointer-events-none absolute inset-0 size-full -rotate-90">
          <circle
            cx="50"
            cy="50"
            r="48"
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray={RING}
            strokeDashoffset={RING * (1 - progress)}
          />
        </svg>
      )}
      {(mode === 'paused' || (mode === 'preview' && !autoplay)) && (
        <span className="absolute inset-0 flex items-center justify-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-plate/70 text-on-plate">
            <Icon name="play" size={20} strokeWidth={2.4} />
          </span>
        </span>
      )}
      <span className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full bg-plate/70 px-2 py-0.5 text-[11px] font-bold text-on-plate tabular-nums">
        {formatSeconds(Math.max(0, left))}
        {mode === 'preview' && <Icon name="muted" size={11} strokeWidth={2.4} />}
      </span>
    </button>
  )
}

/** The live picture while a circle is being recorded, mirrored like a selfie camera. */
export function CirclePreview({ stream }: { stream: MediaStream }) {
  const video = useRef<HTMLVideoElement | null>(null)
  useEffect(() => {
    if (video.current) video.current.srcObject = stream
  }, [stream])
  return (
    <div className="flex justify-center pb-2">
      <video ref={video} autoPlay muted playsInline aria-hidden className="size-[220px] -scale-x-100 rounded-full bg-surface object-cover" />
    </div>
  )
}
