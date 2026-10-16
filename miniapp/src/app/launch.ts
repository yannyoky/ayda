import { startParam } from '../telegram/webapp'

const UUID_HEX = /^([cq])([0-9a-f]{8})([0-9a-f]{4})([0-9a-f]{4})([0-9a-f]{4})([0-9a-f]{12})$/

/** Where a launch link from a bot notice points: `c<chat id as 32 hex>` opens that chat,
 * `q<co-op id as 32 hex>` that co-op quest. */
export function launchPath(param = startParam()): string {
  const match = UUID_HEX.exec(param ?? '')
  if (!match) return '/'
  const id = match.slice(2).join('-')
  return match[1] === 'c' ? `/chats/${id}` : `/coops/${id}`
}
