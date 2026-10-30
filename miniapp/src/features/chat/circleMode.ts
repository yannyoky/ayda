/** How a circle is shown, like in Telegram: a silent loop, played once with sound, or paused. */
export type CircleMode = 'preview' | 'playing' | 'paused'

/** What a tap on a circle in `mode` leads to. */
export function afterTap(mode: CircleMode): CircleMode {
  return mode === 'playing' ? 'paused' : 'playing'
}
