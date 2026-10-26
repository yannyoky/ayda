import { useState } from 'react'
import { initial, tintOf, type AvatarUser } from './avatarTint'

/** Telegram avatar, or the first letter on a tinted tile when there is none or it fails to load. */
export function Avatar({ user, size = 40 }: { user: AvatarUser; size?: number }) {
  const radius = Math.round(size * 0.35)
  const [broken, setBroken] = useState<string | null>(null)
  if (user.avatar_url && broken !== user.avatar_url) {
    const url = user.avatar_url
    return (
      <img
        src={url}
        alt=""
        width={size}
        height={size}
        onError={() => setBroken(url)}
        className="shrink-0 object-cover"
        style={{ width: size, height: size, borderRadius: radius }}
      />
    )
  }
  const tint = tintOf(user)
  return (
    <span
      aria-hidden="true"
      data-tint={tint}
      className="flex shrink-0 items-center justify-center font-display font-bold"
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        fontSize: size * 0.4,
        background: `var(--color-avatar-${tint})`,
        color: `var(--color-avatar-${tint}-ink)`,
      }}
    >
      {initial(user.first_name)}
    </span>
  )
}
