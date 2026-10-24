import { useCallback, useEffect, useRef, useState } from 'react'

export type RecordingKind = 'voice' | 'video_note'

/** The server keeps at most 5 minutes of voice and 60 seconds of a circle (ADR 0019). */
export const MAX_SECONDS: Record<RecordingKind, number> = { voice: 300, video_note: 60 }
// Chrome and Android WebView record WebM (Opus, VP8); Safari records MP4 (AAC, H.264).
const PREFERRED: Record<RecordingKind, string[]> = {
  voice: ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/webm'],
  video_note: ['video/webm;codecs=vp8,opus', 'video/mp4', 'video/webm'],
}
const FALLBACK: Record<RecordingKind, string> = { voice: 'audio/webm', video_note: 'video/webm' }

export function canRecord(): boolean {
  return typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
}

function mimeType(kind: RecordingKind): string | undefined {
  return PREFERRED[kind].find((type) => MediaRecorder.isTypeSupported?.(type))
}

function constraints(kind: RecordingKind): MediaStreamConstraints {
  if (kind === 'voice') return { audio: true }
  return { audio: true, video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 640 } } }
}

export type RecorderState = 'idle' | 'starting' | 'recording'

/** Tap to start, tap to send or cancel. The microphone and camera are released as soon as
 *  recording ends. A circle shows its live picture through `stream`. */
export function useRecorder() {
  const [state, setState] = useState<RecorderState>('idle')
  const [kind, setKind] = useState<RecordingKind>('voice')
  const [seconds, setSeconds] = useState(0)
  const [denied, setDenied] = useState<RecordingKind | null>(null)
  const [stream, setStream] = useState<MediaStream | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const timer = useRef<number | null>(null)
  const done = useRef<((blob: Blob | null) => void) | null>(null)

  const release = useCallback(() => {
    if (timer.current !== null) window.clearInterval(timer.current)
    timer.current = null
    recorder.current?.stream.getTracks().forEach((track) => track.stop())
    recorder.current = null
    setStream(null)
    setState('idle')
    setSeconds(0)
  }, [])

  useEffect(
    () => () => {
      done.current = null
      if (recorder.current?.state === 'recording') recorder.current.stop()
      release()
    },
    [release],
  )

  /** Resolves with the recording once `stop` is called, or null after `cancel`. */
  const start = useCallback(
    async (what: RecordingKind): Promise<Blob | null> => {
      if (state !== 'idle') return null
      setState('starting')
      setKind(what)
      setDenied(null)
      let media: MediaStream
      try {
        media = await navigator.mediaDevices.getUserMedia(constraints(what))
      } catch {
        setDenied(what)
        setState('idle')
        return null
      }
      const type = mimeType(what)
      const options: MediaRecorderOptions = type ? { mimeType: type } : {}
      // About 7 MB a minute: the server re-encodes to 480x480 anyway.
      if (what === 'video_note') options.videoBitsPerSecond = 900_000
      const rec = new MediaRecorder(media, options)
      recorder.current = rec
      chunks.current = []
      const result = new Promise<Blob | null>((resolve) => {
        done.current = resolve
      })
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data)
      }
      rec.onstop = () => {
        const finish = done.current
        done.current = null
        const blob = new Blob(chunks.current, { type: rec.mimeType || type || FALLBACK[what] })
        release()
        finish?.(blob.size > 0 ? blob : null)
      }
      rec.start()
      setStream(media)
      setState('recording')
      const startedAt = Date.now()
      timer.current = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - startedAt) / 1000)
        setSeconds(elapsed)
        if (elapsed >= MAX_SECONDS[what] && rec.state === 'recording') rec.stop()
      }, 250)
      return result
    },
    [state, release],
  )

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

  return { state, kind, seconds, denied, stream, start, stop, cancel }
}

export function formatSeconds(total: number): string {
  const s = Math.max(0, Math.round(total))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
