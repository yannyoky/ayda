import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'
import type { Schemas } from '../api/client'
import { MAX_PHOTO_BYTES, MAX_VIDEO_BYTES, photoType, uploadMedia, videoType } from '../api/media'
import { useCompleteQuest, useToday } from '../api/queries'
import { formatSeconds, canRecord, useRecorder } from '../features/chat/useRecorder'
import { CirclePreview } from '../features/chat/VideoNote'
import { expectedPoints, VISIBILITY_MULTIPLIER } from '../features/day/scoring'
import { plural, t } from '../i18n'
import { useBackButton } from '../telegram/useBackButton'
import { haptic } from '../telegram/webapp'
import { Icon } from '../ui/Icon'
import { CategoryIcon } from '../ui/quest'
import { InlineError, PrimaryButton, Splash } from '../ui/states'

// `routine` is kept in the contract only for older quests; it is no longer offered.
type Visibility = Exclude<Schemas['Visibility'], 'routine'>
const visibilities: Visibility[] = ['friends', 'personal']
const MAX_PHOTOS = 3

interface Picked {
  file: File
  preview: string
}

/** A video picked from the phone or a circle recorded right here; goes without photos. */
interface Clip {
  kind: 'video' | 'video_note'
  blob: Blob
  preview: string
}

/** US-09/US-10: mark a taken quest done, post it to the feed (text, up to 3 photos, one video
 *  or one circle) or keep it to myself. */
export function CompleteScreen() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const today = useToday()
  const complete = useCompleteQuest()
  const [visibility, setVisibility] = useState<Visibility>('friends')
  const [photos, setPhotos] = useState<Picked[]>([])
  const [clip, setClip] = useState<Clip | null>(null)
  const recorder = useRecorder()
  const [caption, setCaption] = useState('')
  const [photoError, setPhotoError] = useState<string | null>(null)
  const [uploading, setUploading] = useState<{ done: number; total: number } | null>(null)
  const [uploadFailed, setUploadFailed] = useState(false)
  const [result, setResult] = useState<Schemas['Completion'] | null>(null)
  const back = useCallback(() => navigate('/'), [navigate])
  useBackButton(back)

  // Free preview URLs when photos are removed or the screen closes
  const previews = useRef<string[]>([])
  useEffect(() => {
    previews.current = [...photos.map((p) => p.preview), ...(clip ? [clip.preview] : [])]
  }, [photos, clip])
  useEffect(() => () => previews.current.forEach((u) => URL.revokeObjectURL?.(u)), [])

  if (result) return <Success result={result} />
  const day = today.data
  if (!day) return <Splash />
  const quest = day.quests.find((q) => q.id === id)
  if (!quest || quest.state !== 'taken') return <Navigate to="/" replace />

  const inFeed = visibility === 'friends'
  const busy = uploading !== null || complete.isPending || recorder.state !== 'idle'

  function addFiles(files: FileList | null) {
    setPhotoError(null)
    const next = [...photos]
    for (const file of Array.from(files ?? [])) {
      if (next.length >= MAX_PHOTOS) break
      if (!photoType(file)) {
        setPhotoError(t.complete.photoWrongType)
        continue
      }
      if (file.size > MAX_PHOTO_BYTES) {
        setPhotoError(t.complete.photoTooBig)
        continue
      }
      next.push({ file, preview: URL.createObjectURL?.(file) ?? '' })
    }
    setPhotos(next)
  }

  function pickVideo(files: FileList | null) {
    setPhotoError(null)
    const file = files?.[0]
    if (!file) return
    if (!videoType(file)) return setPhotoError(t.complete.videoWrongType)
    if (file.size > MAX_VIDEO_BYTES) return setPhotoError(t.complete.videoTooBig)
    setClip({ kind: 'video', blob: file, preview: URL.createObjectURL?.(file) ?? '' })
  }

  async function recordCircle() {
    setPhotoError(null)
    const blob = await recorder.start('video_note')
    if (!blob) return
    if (blob.size > MAX_VIDEO_BYTES) return setPhotoError(t.complete.videoTooBig)
    setClip({ kind: 'video_note', blob, preview: URL.createObjectURL?.(blob) ?? '' })
  }

  function removeClip() {
    if (clip) URL.revokeObjectURL?.(clip.preview)
    setClip(null)
  }

  function removePhoto(index: number) {
    const removed = photos[index]
    if (removed) URL.revokeObjectURL?.(removed.preview)
    setPhotos(photos.filter((_, i) => i !== index))
  }

  async function submit() {
    setUploadFailed(false)
    const mediaIds: string[] = []
    try {
      if (inFeed && clip) {
        setUploading({ done: 0, total: 1 })
        mediaIds.push(await uploadMedia(clip.kind, clip.blob))
      } else if (inFeed && photos.length > 0) {
        setUploading({ done: 0, total: photos.length })
        for (const [i, p] of photos.entries()) {
          mediaIds.push(await uploadMedia('photo', p.file))
          setUploading({ done: i + 1, total: photos.length })
        }
      }
    } catch {
      setUploading(null)
      setUploadFailed(true)
      haptic('error')
      return
    }
    try {
      setUploading(null)
      const body: Schemas['CompleteQuestInput'] = inFeed
        ? { visibility, media_ids: mediaIds, ...(caption.trim() ? { caption: caption.trim() } : {}) }
        : { visibility }
      const completion = await complete.mutateAsync({ id: quest!.id, body })
      haptic('success')
      setResult(completion)
    } catch {
      setUploading(null)
      haptic('error')
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-3 px-4 pt-[max(20px,env(safe-area-inset-top))] pb-8">
      <header className="flex items-center gap-3 px-1">
        <CategoryIcon category={quest.category} dark />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[13px] font-semibold text-muted">{t.complete.title}</span>
          <h1 className="m-0 font-display text-xl leading-tight font-bold">{quest.title}</h1>
        </div>
        <button type="button" aria-label={t.pick.close} onClick={back} className="flex size-11 shrink-0 items-center justify-center rounded-full bg-surface">
          <Icon name="close" size={20} strokeWidth={2.2} />
        </button>
      </header>

      <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
        <legend className="mb-2 px-1 font-display text-sm font-bold">{t.complete.who}</legend>
        {visibilities.map((v) => (
          <label
            key={v}
            className="flex items-center gap-3 rounded-card bg-surface p-4 has-[:checked]:bg-plate has-[:checked]:text-on-plate has-[:focus-visible]:outline-2"
          >
            <input type="radio" name="visibility" value={v} checked={visibility === v} onChange={() => setVisibility(v)} className="sr-only" />
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="text-[15px] font-extrabold">{t.complete.options[v].title}</span>
              <span className="text-xs font-semibold opacity-70">{t.complete.options[v].text}</span>
            </span>
            <span className="flex flex-col items-end">
              <span className="text-sm font-extrabold">{t.complete.expected(expectedPoints(quest.base_points, v, day))}</span>
              <span className="text-xs font-semibold opacity-70">{t.complete.multiplier(VISIBILITY_MULTIPLIER[v])}</span>
            </span>
          </label>
        ))}
      </fieldset>

      {inFeed && (
        <PhotoSection
          photos={photos}
          clip={clip}
          caption={caption}
          error={recorder.denied ? t.chats.cameraDenied : photoError}
          onAdd={addFiles}
          onRemove={removePhoto}
          onVideo={pickVideo}
          onCircle={canRecord() ? () => void recordCircle() : null}
          onRemoveClip={removeClip}
          onCaption={setCaption}
        />
      )}

      {recorder.state === 'recording' && (
        <section aria-label={t.complete.circle} className="flex flex-col items-center gap-2 rounded-card bg-surface p-4">
          {recorder.stream && <CirclePreview stream={recorder.stream} />}
          <div className="flex w-full items-center gap-2">
            <button type="button" onClick={recorder.cancel} aria-label={t.chats.cancelRecording} className="flex size-12 shrink-0 items-center justify-center rounded-field bg-bg">
              <Icon name="close" size={20} strokeWidth={2.2} />
            </button>
            <span role="timer" className="flex-1 text-center text-sm font-extrabold tabular-nums">
              {t.chats.recording(formatSeconds(recorder.seconds))}
            </span>
            <button type="button" onClick={recorder.stop} aria-label={t.complete.circleDone} className="flex size-12 shrink-0 items-center justify-center rounded-field bg-accent text-on-accent">
              <Icon name="check" size={20} strokeWidth={2.4} />
            </button>
          </div>
        </section>
      )}

      {uploadFailed && <InlineError text={t.complete.uploadFailed} />}
      {complete.isError && <InlineError text={complete.error.message} />}
      <PrimaryButton disabled={busy} onClick={() => void submit()} className="mt-auto">
        {uploading ? (clip ? t.complete.uploadingVideo : t.complete.uploading(uploading.done, uploading.total)) : t.complete.submit}
      </PrimaryButton>
    </main>
  )
}

const tile =
  'flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-tile border-2 border-dashed border-track bg-transparent text-xs font-bold text-muted has-[:focus-visible]:outline-2'

function PhotoSection({
  photos,
  clip,
  caption,
  error,
  onAdd,
  onRemove,
  onVideo,
  onCircle,
  onRemoveClip,
  onCaption,
}: {
  photos: Picked[]
  clip: Clip | null
  caption: string
  error: string | null
  onAdd: (files: FileList | null) => void
  onRemove: (index: number) => void
  onVideo: (files: FileList | null) => void
  /** Null when this browser can't record. */
  onCircle: (() => void) | null
  onRemoveClip: () => void
  onCaption: (text: string) => void
}) {
  const fileId = useId()
  const videoId = useId()
  const captionId = useId()
  return (
    <section aria-label={t.complete.photos} className="flex flex-col gap-3 rounded-card bg-surface p-4">
      {clip && (
        <div className="relative flex justify-center">
          {clip.preview && (
            <video
              src={clip.preview}
              controls
              playsInline
              aria-label={clip.kind === 'video_note' ? t.complete.circle : t.complete.video}
              className={clip.kind === 'video_note' ? 'size-[200px] rounded-full bg-bg object-cover' : 'max-h-[320px] w-full rounded-tile bg-bg'}
            />
          )}
          <button
            type="button"
            aria-label={clip.kind === 'video_note' ? t.complete.removeCircle : t.complete.removeVideo}
            onClick={onRemoveClip}
            className="absolute top-1 right-1 flex size-8 items-center justify-center rounded-full bg-plate text-on-plate"
          >
            <Icon name="close" size={16} strokeWidth={2.4} />
          </button>
        </div>
      )}
      {!clip && (
        <div className="grid grid-cols-3 gap-2">
          {photos.map((p, i) => (
            <div key={p.preview || i} className="relative aspect-square overflow-hidden rounded-tile bg-bg">
              {p.preview && <img src={p.preview} alt="" className="size-full object-cover" />}
              <button
                type="button"
                aria-label={t.complete.removePhoto(i + 1)}
                onClick={() => onRemove(i)}
                className="absolute top-1 right-1 flex size-8 items-center justify-center rounded-full bg-plate text-on-plate"
              >
                <Icon name="close" size={16} strokeWidth={2.4} />
              </button>
            </div>
          ))}
          {photos.length < MAX_PHOTOS && (
            <label htmlFor={fileId} className={tile}>
              <Icon name="camera" size={22} />
              {t.complete.addPhoto}
              <input
                id={fileId}
                type="file"
                accept="image/jpeg,image/png,image/heic,image/heif,image/webp"
                multiple
                onChange={(e) => {
                  onAdd(e.target.files)
                  e.target.value = ''
                }}
                className="sr-only"
              />
            </label>
          )}
          {photos.length === 0 && (
            <label htmlFor={videoId} className={tile}>
              <Icon name="play" size={22} />
              {t.complete.addVideo}
              <input
                id={videoId}
                type="file"
                accept="video/mp4,video/quicktime,video/webm"
                onChange={(e) => {
                  onVideo(e.target.files)
                  e.target.value = ''
                }}
                className="sr-only"
              />
            </label>
          )}
          {photos.length === 0 && onCircle && (
            <button type="button" onClick={onCircle} className={tile}>
              <Icon name="camera" size={22} />
              {t.complete.recordCircle}
            </button>
          )}
        </div>
      )}
      <span className="text-xs font-semibold text-muted">{error ?? (clip ? t.complete.videoHint : t.complete.photosHint)}</span>
      <label htmlFor={captionId} className="sr-only">
        {t.complete.caption}
      </label>
      <textarea
        id={captionId}
        rows={2}
        maxLength={500}
        value={caption}
        placeholder={t.complete.captionPlaceholder}
        onChange={(e) => onCaption(e.target.value)}
        className="resize-none rounded-field border-0 bg-bg p-3 text-[15px] font-medium placeholder:text-muted"
      />
    </section>
  )
}

function Success({ result }: { result: Schemas['Completion'] }) {
  const b = result.points_breakdown
  return (
    <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-3 px-4 pt-[max(20px,env(safe-area-inset-top))] pb-8">
      <section role="status" className="flex flex-1 flex-col items-center justify-center gap-4 rounded-card bg-accent p-6 text-center text-on-accent">
        <span className="font-display text-lg font-bold">{t.complete.successTitle}</span>
        <span className="font-display text-[88px] leading-none font-extrabold tracking-[-4px]">+{result.points_awarded}</span>
        <span className="text-sm font-bold">{t.complete.breakdown(b.base, b.visibility_multiplier, b.streak_multiplier)}</span>
        {(result.coop_bonus ?? 0) > 0 && <span className="text-base font-extrabold">{t.complete.coopBonus(result.coop_bonus ?? 0)}</span>}
        <span className="rounded-[10px] bg-surface px-3 py-1.5 text-sm font-extrabold text-ink">
          {t.complete.streak(result.streak.current_days, plural(result.streak.current_days, t.today.days))}
        </span>
      </section>
      <div className="flex gap-2">
        {result.post_id && (
          <Link to="/feed" className="flex h-14 flex-1 items-center justify-center rounded-[20px] bg-surface text-base font-extrabold text-ink no-underline">
            {t.complete.toFeed}
          </Link>
        )}
        <Link to="/" className="flex h-14 flex-1 items-center justify-center rounded-[20px] bg-plate text-base font-extrabold text-on-plate no-underline">
          {t.complete.toToday}
        </Link>
      </div>
    </main>
  )
}
