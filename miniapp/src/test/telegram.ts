import { vi } from 'vitest'
import type { TelegramWebApp } from '../telegram/webapp'

/** Installs a fake `window.Telegram.WebApp`; returns it for assertions. */
export function fakeTelegram(initData: string, startParam?: string): TelegramWebApp {
  const app: TelegramWebApp = {
    initData,
    initDataUnsafe: startParam ? { start_param: startParam } : {},
    platform: 'ios',
    ready: vi.fn(),
    expand: vi.fn(),
    setHeaderColor: vi.fn(),
    setBackgroundColor: vi.fn(),
    setBottomBarColor: vi.fn(),
    openTelegramLink: vi.fn(),
    openLink: vi.fn(),
    close: vi.fn(),
    BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() },
    HapticFeedback: { impactOccurred: vi.fn(), notificationOccurred: vi.fn(), selectionChanged: vi.fn() },
  }
  window.Telegram = { WebApp: app }
  return app
}
