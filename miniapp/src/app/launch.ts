import { startParam } from '../telegram/webapp'

/** Where a launch link points: `c<conversation id as 32 hex>` opens that chat (bot notices). */
export function launchPath(param = startParam()): string {
  const chat = /^c([0-9a-f]{8})([0-9a-f]{4})([0-9a-f]{4})([0-9a-f]{4})([0-9a-f]{12})$/.exec(param ?? '')
  return chat ? `/chats/${chat.slice(1).join('-')}` : '/'
}
