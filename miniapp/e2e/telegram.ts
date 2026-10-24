import { createHmac } from 'node:crypto'
import type { Page } from '@playwright/test'

/** Must match TELEGRAM_BOT_TOKEN of the backend under test (see playwright.config.ts). */
export const E2E_BOT_TOKEN = process.env.E2E_BOT_TOKEN ?? '123456:E2E-TOKEN'

/** initData signed the way Telegram signs it, so the real backend accepts it (US-01). */
export function signedInitData(user: { id: number; first_name: string }, botToken = E2E_BOT_TOKEN): string {
  const fields: Record<string, string> = {
    query_id: 'AAE2E',
    user: JSON.stringify({ ...user, language_code: 'ru' }),
    auth_date: String(Math.floor(Date.now() / 1000)),
  }
  const check = Object.keys(fields)
    .sort()
    .map((k) => `${k}=${fields[k]}`)
    .join('\n')
  const secret = createHmac('sha256', 'WebAppData').update(botToken).digest()
  const hash = createHmac('sha256', secret).update(check).digest('hex')
  return new URLSearchParams({ ...fields, hash }).toString()
}

/** Replaces Telegram's bridge script with a stub that opens the app as a signed-in user. */
export async function openAsTelegramUser(page: Page, user: { id: number; first_name: string }): Promise<void> {
  const initData = signedInitData(user)
  await page.route('https://telegram.org/js/telegram-web-app.js*', (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: `
        const noop = () => {}
        window.Telegram = { WebApp: {
          initData: ${JSON.stringify(initData)},
          initDataUnsafe: {},
          platform: 'e2e',
          ready: noop, expand: noop, close: noop,
          setHeaderColor: noop, setBackgroundColor: noop, setBottomBarColor: noop,
          openTelegramLink: noop, openLink: noop,
          BackButton: { show: noop, hide: noop, onClick: noop, offClick: noop },
          HapticFeedback: { impactOccurred: noop, notificationOccurred: noop, selectionChanged: noop },
        } }`,
    }),
  )
  await page.goto('/')
}
