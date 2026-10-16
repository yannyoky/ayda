/** Telegram avatar, or the first letter on a plate when there is none. */
export function Avatar({ user, size = 40 }: { user: { first_name: string; avatar_url?: string | null }; size?: number }) {
  const radius = Math.round(size * 0.35)
  if (user.avatar_url) {
    return <img src={user.avatar_url} alt="" width={size} height={size} className="shrink-0 object-cover" style={{ borderRadius: radius }} />
  }
  return (
    <span
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center bg-plate font-display font-bold text-accent"
      style={{ width: size, height: size, borderRadius: radius, fontSize: size * 0.36 }}
    >
      {user.first_name.charAt(0).toUpperCase()}
    </span>
  )
}
