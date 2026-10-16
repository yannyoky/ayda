import { useState } from 'react'
import { Link } from 'react-router'
import type { Schemas } from '../api/client'
import { useFeed, useMe } from '../api/queries'
import { CommentsSheet } from '../features/feed/CommentsSheet'
import { PostCard } from '../features/feed/PostCard'
import { t } from '../i18n'
import { ScreenHeader } from '../ui/primitives'
import { InlineError } from '../ui/states'

/** US-13: proofs and routines of me and my friends, newest first, 20 per page. */
export function FeedScreen() {
  const me = useMe().data as Schemas['Me']
  const feed = useFeed()
  const [commentsFor, setCommentsFor] = useState<string | null>(null)
  const posts = feed.data?.pages.flatMap((p) => p.items) ?? []

  return (
    <>
      <ScreenHeader title={t.feed.title} />
      {feed.isError && <InlineError onRetry={() => void feed.refetch()} />}
      {feed.isSuccess && posts.length === 0 && (
        <div className="flex flex-col gap-3 rounded-card bg-surface p-4">
          <p className="m-0 text-[15px] font-semibold text-muted">{t.feed.empty}</p>
          <Link to="/friends" className="flex h-12 items-center justify-center rounded-field bg-plate font-extrabold text-on-plate no-underline">
            {t.feed.inviteCta}
          </Link>
        </div>
      )}
      {posts.map((post) => (
        <PostCard key={post.id} post={post} mine={post.author.id === me.id} onComments={() => setCommentsFor(post.id)} />
      ))}
      {feed.hasNextPage && (
        <button
          type="button"
          disabled={feed.isFetchingNextPage}
          onClick={() => void feed.fetchNextPage()}
          className="h-12 rounded-field bg-surface text-sm font-extrabold disabled:opacity-60"
        >
          {t.feed.more}
        </button>
      )}
      {commentsFor && <CommentsSheet postId={commentsFor} onClose={() => setCommentsFor(null)} />}
    </>
  )
}
