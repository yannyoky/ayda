import { startParam } from '../telegram/webapp'

const UUID_HEX = /^([cq])([0-9a-f]{8})([0-9a-f]{4})([0-9a-f]{4})([0-9a-f]{4})([0-9a-f]{12})$/

/** Where a launch link from a bot notice points: `c<chat id as 32 hex>` opens that chat,
 * `q<co-op id as 32 hex>` that co-op quest, `signout` the "sign out everywhere" screen
 * (the bot's notice about a sign-in on another device, ayda.app.security). */
export const SIGN_OUT_PARAM = 'signout'

export function launchPath(param = startParam()): string {
  if (param === SIGN_OUT_PARAM) return '/signout'
  const match = UUID_HEX.exec(param ?? '')
  if (!match) return '/'
  const id = match.slice(2).join('-')
  return match[1] === 'c' ? `/chats/${id}` : `/coops/${id}`
}
