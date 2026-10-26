import { Icon } from './Icon'

/** The assistant's face: a spark on the accent tile, so her chat never looks like a friend's. */
export function AydaMark({ size = 40 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center bg-accent text-on-accent"
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.35) }}
    >
      <Icon name="spark" size={Math.round(size * 0.5)} strokeWidth={2.2} filled />
    </span>
  )
}
