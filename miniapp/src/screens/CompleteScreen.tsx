import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'
import type { Schemas } from '../api/client'
import { MAX_PHOTO_BYTES, photoType, uploadPhoto } from '../api/media'
import { useCompleteQuest, useToday } from '../api/queries'
import { expectedPoints, VISIBILITY_MULTIPLIER } from '../features/day/scoring'
import { plural, t } from '../i18n'
import { useBackButton } from '../telegram/useBackButton'
import { haptic } from '../telegram/webapp'
import { Icon } from '../ui/Icon'
import { CategoryIcon } from '../ui/quest'
import { InlineError, PrimaryButton, Splash } from '../ui/states'

type Visibility = Schemas['Visibility']
const visibilities: Visibility[] = ['friends', 'routine', 'personal']
const MAX_PHOTOS = 3

interface Picked {
  file: File
  preview: string
}

/** US-09/US-10: mark a taken quest done, choose who sees it, attach 1-3 photos for friends. */
export function CompleteScreen() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const today = useToday()
  const complete = useCompleteQuest()
  const [visibility, setVisibility] = useState<Visibility>('friends')
  const [photos, setPhotos] = useState<Picked[]>([])
  const [caption, setCaption] = useState('')
  const [photoError, setPhotoError] = useState<string | null>(null)
  const [uploading, setUploading] = useState<{ done: number; total: number } | null>(null)
  const [result, setResult] = useState<Schemas['Completion'] | null>(null)
  const back = useCallback(() => navigate('/'), [navigate])
  useBackButton(back)

  // Free preview URLs when photos are removed or the screen closes
  const previews = useRef<string[]>([])
  useEffect(() => {
    previews.current = photos.map((p) => p.preview)
  }, [photos])
  useEffect(() => () => previews.current.forEach((u) => URL.revokeObjectURL?.(u)), [])

  if (result) return <Success result={result} />
  const day = today.data
  if (!day) return <Splash />
  const quest = day.quests.find((q) => q.id === id)
  if (!quest || quest.state !== 'taken') return <Navigate to="/" replace />

  const needPhotos = visibility === 'friends'
  const ready = !needPhotos || photos.length > 0
  const busy = uploading !== null || complete.isPending

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

  function removePhoto(index: number) {
    const removed = photos[index]
    if (removed) URL.revokeObjectURL?.(removed.preview)
    setPhotos(photos.filter((_, i) => i !== index))
  }

  async function submit() {
    try {
      const mediaIds: string[] = []
      if (needPhotos) {
        setUploading({ done: 0, total: photos.length })
        for (const [i, p] of photos.entries()) {
          mediaIds.push(await uploadPhoto(p.file))
          setUploading({ done: i + 1, total: photos.length })
        }
      }
      setUploading(null)
      const body: Schemas['CompleteQuestInput'] = needPhotos
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

      {needPhotos && (
        <PhotoSection
          photos={photos}
          caption={caption}
          error={photoError}
          onAdd={addFiles}
          onRemove={removePhoto}
          onCaption={setCaption}
        />
      )}

      {complete.isError && <InlineError text={complete.error.message} />}
      <PrimaryButton disabled={!ready || busy} onClick={() => void submit()} className="mt-auto">
        {uploading ? t.complete.uploading(uploading.done, uploading.total) : t.complete.submit}
      </PrimaryButton>
    </main>
  )
}

function PhotoSection({
  photos,
  caption,
  error,
  onAdd,
  onRemove,
  onCaption,
}: {
  photos: Picked[]
  caption: string
  error: string | null
  onAdd: (files: FileList | null) => void
  onRemove: (index: number) => void
  onCaption: (text: string) => void
}) {
  const fileId = useId()
  const captionId = useId()
  return (
    <section aria-label={t.complete.photos} className="flex flex-col gap-3 rounded-card bg-surface p-4">
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
          <label
            htmlFor={fileId}
            className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-tile border-2 border-dashed border-track text-xs font-bold text-muted has-[:focus-visible]:outline-2"
          >
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
      </div>
      <span className="text-xs font-semibold text-muted">{error ?? t.complete.photosHint}</span>
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
