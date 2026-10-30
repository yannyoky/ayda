# Ayda: themes

English · [Русский](../ru/design/themes.md)

Layout: option A (bento widgets) from the canvas https://claude.ai/artifact/BwWpCYXb7tuPM8ov2S7L6R
Fonts: Unbounded (headings, large numbers), Manrope (body text). Both support Cyrillic.
Radii: cards 28px, icon tiles 14px, inputs and buttons 16px, tab bar 32px; media (photos, video) and chat bubbles 20px, segments inside a 16px control 12px, chips 10px. In code they are the `rounded-card`, `rounded-tile`, `rounded-field`, `rounded-bar`, `rounded-media`, `rounded-bubble`, `rounded-segment` and `rounded-chip` classes; no raw pixel radii.

| Token | Purpose | A6 · Graphite | A2 · Plum |
|---|---|---|---|
| `bg` | screen background, chips, icon backdrops | `#E9E9E7` | `#F1E9E4` |
| `surface` | cards | `#FFFFFF` | `#FFFFFF` |
| `plate` | dark plates (check-in, tab bar) | `#222326` | `#3B1E3F` |
| `plate-2` | input field on a plate | `#34363B` | `#553258` |
| `ink` | primary text and icons | `#18191B` | `#2A1830` |
| `muted` | secondary text | `#5B5D62` | `#6E5A69` |
| `track` | inactive chart bars | `#D6D6D3` | `#E6D7D2` |
| `accent` | streak, active tab, CTA | `#FF5FA2` | `#FF9E7A` |
| `on-plate` | text on a plate | `#FFFFFF` | `#FFFFFF` |
| `on-accent` | text on the accent | = `ink` | = `ink` |

## Letter avatars

A user without a Telegram photo gets the first character of the name (a whole emoji or letter, never half of one) on one of six tints. The tint is picked from the user id, so a friend has the same colour everywhere.

| Tint | Graphite tile / letter | Plum tile / letter |
|---|---|---|
| 1 | `#222326` / `#FF5FA2` | `#3B1E3F` / `#FF9E7A` |
| 2 | `#FF5FA2` / `ink` | `#FF9E7A` / `ink` |
| 3 | `#FFD25E` / `ink` | `#F6C977` / `ink` |
| 4 | `#8EC5FF` / `ink` | `#A9C8E8` / `ink` |
| 5 | `#A8E0A0` / `ink` | `#B9DDB8` / `ink` |
| 6 | `#C9B6FF` / `ink` | `#E3B4D6` / `ink` |

The assistant has its own mark: a spark on the accent tile, next to its messages and in its chat header.

## Motion

Motion only explains a change or answers a touch. Frequent actions (tabs, scrolling, typing, likes) do not animate.

| What | How | Time |
|---|---|---|
| Press on any button | scale to 0.97 | 160ms, `--ease-out` |
| Bottom sheet opens | slides up from the bottom, backdrop fades in | 300ms, `--ease-drawer` |
| Bottom sheet closes | slides down (also by a swipe or a flick on its top) | 200ms |
| Segmented control | one pill slides to the chosen option | 250ms |
| Streak grew since the last visit | the number rolls up once | 420ms |
| Quest marked done | check pops, sparks fly out, points count up, success haptic | 360–700ms |

Curves: `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`, `--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)`. Only `transform` and `opacity` move. With `prefers-reduced-motion` the movement is dropped and only fades stay.

On Android the same tokens live in `mobile/shared` (`Palette.avatars`, `AvatarTints`, `Radii`, `Motion`; the tint hash matches the Mini App's, so a friend has one colour on both). Bottom sheets are Material `ModalBottomSheet`, which already slides up and closes by a swipe or a flick. With "Remove animations" in the system settings Compose finishes every animation at once.
