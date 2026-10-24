import { useEffect, useRef, useState } from 'react'
import type { Schemas } from '../../api/client'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'
import { formatSeconds } from './useRecorder'

interface Props {
  attachment: Schemas['Attachment']
  /** The play link is short-lived: ask for fresh messages when it stops working. */
  onExpired: () => void
}

/** A circle ("кружок"): a round video that plays with sound on tap. */
export function VideoNote({ attachment, onExpired }: Props) {
  const video = useRef<HTMLVideoElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const [position, setPosition] = useState(0)
  const total = (attachment.duration_ms ?? 0) / 1000

  useEffect(() => () => video.current?.pause(), [])

  if (attachment.status !== 'ready' || !attachment.url) {
    const text = attachment.status === 'expired' ? t.chats.circleExpired : attachment.status === 'failed' ? t.chats.circleFailed : t.chats.circleProcessing
    return (
      <span className="flex size-[200px] items-center justify-center rounded-full bg-surface p-6 text-center text-sm font-bold text-muted">{text}</span>
    )
  }

  function toggle() {
    const el = video.current
    if (!el) return
    if (el.paused) void el.play().catch(() => setPlaying(false))
    else el.pause()
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={playing ? t.chats.circlePause : t.chats.circlePlay}
      className="relative block size-[200px] overflow-hidden rounded-full bg-surface p-0"
    >
      <video
        ref={video}
        src={attachment.url}
        preload="metadata"
        playsInline
        className="size-full object-cover"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false)
          setPosition(0)
        }}
        onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
        onError={onExpired}
      />
      {!playing && (
        <span className="absolute inset-0 flex items-center justify-center">
          <span className="flex size-12 items-center justify-center rounded-full bg-plate/70 text-on-plate">
            <Icon name="play" size={20} strokeWidth={2.4} />
          </span>
        </span>
      )}
      <span className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-plate/70 px-2 py-0.5 text-[11px] font-bold text-on-plate tabular-nums">
        {formatSeconds(playing ? total - position : total)}
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
