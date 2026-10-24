import { useEffect, useRef, useState } from 'react'
import type { Schemas } from '../../api/client'
import { t } from '../../i18n'
import { Icon } from '../../ui/Icon'
import { formatSeconds } from './useRecorder'

interface Props {
  attachment: Schemas['Attachment']
  mine: boolean
  /** The play link is short-lived: ask for fresh messages when it stops working. */
  onExpired: () => void
}

/** A voice message: play and pause, with the time left while playing. */
export function VoiceMessage({ attachment, mine, onExpired }: Props) {
  const audio = useRef<HTMLAudioElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const [position, setPosition] = useState(0)
  const total = (attachment.duration_ms ?? 0) / 1000
  const muted = mine ? 'text-on-plate/60' : 'text-muted'

  useEffect(() => () => audio.current?.pause(), [])

  if (attachment.status !== 'ready' || !attachment.url) {
    return (
      <span className={`flex items-center gap-2 text-sm font-bold ${muted}`}>
        <Icon name="mic" size={18} />
        {attachment.status === 'failed' ? t.chats.voiceFailed : t.chats.voiceProcessing}
      </span>
    )
  }

  function toggle() {
    const el = audio.current
    if (!el) return
    if (el.paused) void el.play().catch(() => setPlaying(false))
    else el.pause()
  }

  const progress = total > 0 ? Math.min(1, position / total) : 0
  return (
    <span className="flex min-w-[180px] items-center gap-2.5">
      <audio
        ref={audio}
        src={attachment.url}
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false)
          setPosition(0)
        }}
        onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
        onError={onExpired}
      />
      <button
        type="button"
        onClick={toggle}
        aria-label={playing ? t.chats.voicePause : t.chats.voicePlay}
        className={`flex size-9 shrink-0 items-center justify-center rounded-full ${mine ? 'bg-on-plate/15' : 'bg-bg'}`}
      >
        <Icon name={playing ? 'pause' : 'play'} size={16} strokeWidth={2.4} />
      </button>
      <span className={`h-1 flex-1 overflow-hidden rounded-full ${mine ? 'bg-on-plate/20' : 'bg-bg'}`} aria-hidden>
        <span className="block h-full rounded-full bg-accent" style={{ width: `${progress * 100}%` }} />
      </span>
      <span className={`text-xs font-bold tabular-nums ${muted}`}>{formatSeconds(playing ? total - position : total)}</span>
    </span>
  )
}
