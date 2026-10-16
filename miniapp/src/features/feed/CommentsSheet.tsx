import { useId, useState, type FormEvent } from 'react'
import { useAddComment, useComments, useDeleteComment } from '../../api/queries'
import { formatAgo, t } from '../../i18n'
import { Avatar } from '../../ui/Avatar'
import { Icon } from '../../ui/Icon'
import { Sheet } from '../../ui/Sheet'

export function CommentsSheet({ postId, onClose }: { postId: string; onClose: () => void }) {
  const inputId = useId()
  const comments = useComments(postId)
  const add = useAddComment(postId)
  const remove = useDeleteComment(postId)
  const [text, setText] = useState('')
  const items = comments.data?.items ?? []

  function submit(e: FormEvent) {
    e.preventDefault()
    const value = text.trim()
    if (value) add.mutate(value, { onSuccess: () => setText('') })
  }

  return (
    <Sheet title={t.comments.title} onClose={onClose}>
      {comments.isSuccess && items.length === 0 && <p className="m-0 text-sm font-semibold text-muted">{t.comments.empty}</p>}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {items.map((c) => (
          <li key={c.id} className="flex items-start gap-2.5 rounded-field bg-surface p-3">
            <Avatar user={c.author} size={32} />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-xs font-bold text-muted">
                {c.author.first_name} · {formatAgo(c.created_at)}
              </span>
              <span className="text-[15px] font-medium break-words">{c.text}</span>
            </div>
            {c.can_delete && (
              <button
                type="button"
                aria-label={t.comments.delete}
                onClick={() => remove.mutate(c.id)}
                className="flex size-9 shrink-0 items-center justify-center rounded-tile text-muted"
              >
                <Icon name="close" size={16} />
              </button>
            )}
          </li>
        ))}
      </ul>
      <form onSubmit={submit} className="flex gap-2">
        <label htmlFor={inputId} className="sr-only">
          {t.comments.placeholder}
        </label>
        <input
          id={inputId}
          value={text}
          maxLength={500}
          placeholder={t.comments.placeholder}
          onChange={(e) => setText(e.target.value)}
          className="h-12 min-w-0 flex-1 rounded-field border-0 bg-surface px-4 text-[15px] font-medium placeholder:text-muted"
        />
        <button
          type="submit"
          aria-label={t.comments.send}
          disabled={!text.trim() || add.isPending}
          className="flex size-12 shrink-0 items-center justify-center rounded-field bg-accent text-on-accent disabled:opacity-40"
        >
          <Icon name="arrow" size={20} strokeWidth={2.4} />
        </button>
      </form>
    </Sheet>
  )
}
