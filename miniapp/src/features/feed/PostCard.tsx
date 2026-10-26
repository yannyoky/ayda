import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { Schemas } from '../../api/client'
import { useDeletePost, useToggleLike } from '../../api/queries'
import { VideoNote } from '../chat/VideoNote'
import { formatAgo, formatNumber, t } from '../../i18n'
import { haptic } from '../../telegram/webapp'
import { Avatar } from '../../ui/Avatar'
import { Icon } from '../../ui/Icon'

export function PostCard({ post, mine, onComments }: { post: Schemas['Post']; mine: boolean; onComments: () => void }) {
  const like = useToggleLike()
  const remove = useDeletePost()
  const routine = post.kind === 'routine'
  const name = mine ? t.feed.me : post.author.first_name
  const subtitle = `${routine ? t.feed.routine : (post.quest_title ?? t.quest.categories[post.category])} · ${formatAgo(post.created_at)}`

  return (
    <article aria-label={`${name}: ${routine ? t.feed.routine : (post.quest_title ?? '')}`} className="flex flex-col gap-3 rounded-card bg-surface p-3.5">
      <header className="flex items-center gap-2.5">
        <Avatar user={post.author} size={40} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[15px] font-extrabold break-words">{name}</span>
          <span className="truncate text-xs font-semibold text-muted">{subtitle}</span>
        </div>
        <span className="shrink-0 self-start rounded-chip bg-bg px-2.5 py-1 text-xs font-extrabold whitespace-nowrap">{t.quest.categories[post.category]}</span>
      </header>

      {routine ? (
        <div className="flex items-center gap-2.5 rounded-field bg-bg p-3 text-muted">
          <Icon name="lock" size={20} />
          <span className="text-sm font-semibold">{t.feed.routineHidden}</span>
        </div>
      ) : (
        <>
          {post.photos.length > 0 && <Photos photos={post.photos} />}
          {post.video && <PostVideo video={post.video} />}
          {post.caption && <Caption text={post.caption} />}
        </>
      )}

      <footer className="flex items-center gap-1.5">
        <button
          type="button"
          aria-pressed={post.liked_by_me}
          aria-label={post.liked_by_me ? t.feed.unlike(post.like_count) : t.feed.like(post.like_count)}
          onClick={() => {
            haptic('tap')
            like.mutate({ id: post.id, like: !post.liked_by_me })
          }}
          className={`flex h-11 items-center gap-1.5 rounded-field px-3.5 text-sm font-extrabold ${post.liked_by_me ? 'bg-accent text-on-accent' : 'bg-bg'}`}
        >
          <Icon name="heart" size={18} filled={post.liked_by_me} />
          {formatNumber(post.like_count)}
        </button>
        <button
          type="button"
          aria-label={t.feed.comments(post.comment_count)}
          onClick={onComments}
          className="flex h-11 items-center gap-1.5 rounded-field bg-bg px-3.5 text-sm font-extrabold"
        >
          <Icon name="comment" size={18} />
          {formatNumber(post.comment_count)}
        </button>
        <span className="flex-1" />
        {mine && (
          <button
            type="button"
            aria-label={t.feed.delete}
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(t.feed.deleteConfirm)) remove.mutate(post.id)
            }}
            className="flex size-11 items-center justify-center rounded-field text-muted"
          >
            <Icon name="trash" size={18} />
          </button>
        )}
      </footer>
    </article>
  )
}

/** Long captions fold to four lines; "ещё" opens the rest in place. */
const CAPTION_FOLD = 220

function Caption({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const long = text.length > CAPTION_FOLD
  return (
    <div className="flex flex-col items-start gap-1 px-1">
      <p className={`m-0 text-[15px] leading-snug font-medium [overflow-wrap:anywhere] ${long && !open ? 'line-clamp-4' : ''}`}>{text}</p>
      {long && !open && (
        <button type="button" onClick={() => setOpen(true)} className="text-sm font-extrabold text-muted">
          {t.feed.captionMore}
        </button>
      )}
    </div>
  )
}

/** A proof's video or circle (ADR 0019). The play link is short-lived, so a failed load
 *  refetches the feed; the file itself is gone after 30 days. */
function PostVideo({ video }: { video: Schemas['PostVideo'] }) {
  const client = useQueryClient()
  const refresh = () => void client.invalidateQueries({ queryKey: ['feed'] })
  if (video.kind === 'video_note') {
    return (
      <div className="flex justify-center">
        <VideoNote attachment={video} onExpired={refresh} />
      </div>
    )
  }
  if (video.status !== 'ready' || !video.url) {
    const text = video.status === 'expired' ? t.feed.videoExpired : video.status === 'failed' ? t.feed.videoFailed : t.feed.videoProcessing
    return <span className="flex aspect-video items-center justify-center rounded-media bg-bg p-6 text-center text-sm font-bold text-muted">{text}</span>
  }
  return (
    <video
      src={video.url}
      controls
      playsInline
      preload="metadata"
      aria-label={t.feed.video}
      width={video.width ?? undefined}
      height={video.height ?? undefined}
      onError={refresh}
      className="max-h-[480px] w-full rounded-media bg-plate"
    />
  )
}

function Photos({ photos }: { photos: Schemas['Photo'][] }) {
  return (
    <div className="-mx-1 flex snap-x snap-mandatory gap-2 overflow-x-auto px-1 [scrollbar-width:none]">
      {photos.map((photo, i) => (
        <img
          key={photo.id}
          src={photo.url}
          alt={t.feed.photo(i + 1, photos.length)}
          width={photo.width}
          height={photo.height}
          loading="lazy"
          className={`aspect-[4/3] shrink-0 snap-center rounded-media bg-plate object-cover ${photos.length > 1 ? 'w-[88%]' : 'w-full'}`}
        />
      ))}
    </div>
  )
}
