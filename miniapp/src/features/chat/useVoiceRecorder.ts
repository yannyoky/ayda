import { useCallback, useEffect, useRef, useState } from 'react'

/** The server keeps at most 5 minutes of a voice message (ADR 0019). */
export const MAX_VOICE_SECONDS = 300
// Chrome and Android WebView record Opus in WebM; Safari records AAC in MP4.
const PREFERRED = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/webm']

export function canRecordVoice(): boolean {
  return typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
}

function mimeType(): string | undefined {
  return PREFERRED.find((type) => MediaRecorder.isTypeSupported?.(type))
}

export type RecorderState = 'idle' | 'starting' | 'recording'

/** Tap to start, tap to send or cancel. The microphone is released as soon as recording ends. */
export function useVoiceRecorder() {
  const [state, setState] = useState<RecorderState>('idle')
  const [seconds, setSeconds] = useState(0)
  const [denied, setDenied] = useState(false)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const timer = useRef<number | null>(null)
  const done = useRef<((blob: Blob | null) => void) | null>(null)

  const release = useCallback(() => {
    if (timer.current !== null) window.clearInterval(timer.current)
    timer.current = null
    recorder.current?.stream.getTracks().forEach((track) => track.stop())
    recorder.current = null
    setState('idle')
    setSeconds(0)
  }, [])

  useEffect(() => () => {
    done.current = null
    if (recorder.current?.state === 'recording') recorder.current.stop()
    release()
  }, [release])

  /** Resolves with the recording once `stop` is called, or null after `cancel`. */
  const start = useCallback(async (): Promise<Blob | null> => {
    if (state !== 'idle') return null
    setState('starting')
    setDenied(false)
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      setDenied(true)
      setState('idle')
      return null
    }
    const type = mimeType()
    const media = new MediaRecorder(stream, type ? { mimeType: type } : undefined)
    recorder.current = media
    chunks.current = []
    const result = new Promise<Blob | null>((resolve) => {
      done.current = resolve
    })
    media.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.current.push(e.data)
    }
    media.onstop = () => {
      const finish = done.current
      done.current = null
      const blob = new Blob(chunks.current, { type: media.mimeType || type || 'audio/webm' })
      release()
      finish?.(blob.size > 0 ? blob : null)
    }
    media.start()
    setState('recording')
    const startedAt = Date.now()
    timer.current = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000)
      setSeconds(elapsed)
      if (elapsed >= MAX_VOICE_SECONDS && media.state === 'recording') media.stop()
    }, 250)
    return result
  }, [state, release])

  const stop = useCallback(() => {
    if (recorder.current?.state === 'recording') recorder.current.stop()
  }, [])

  const cancel = useCallback(() => {
    const finish = done.current
    done.current = null
    finish?.(null)
    if (recorder.current?.state === 'recording') recorder.current.stop()
    else release()
  }, [release])

  return { state, seconds, denied, start, stop, cancel }
}

export function formatSeconds(total: number): string {
  const s = Math.max(0, Math.round(total))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
