// Thin typed wrapper over the official `window.Telegram.WebApp` bridge.
// Everything degrades to no-ops outside Telegram (browser dev, tests).

interface TelegramBackButton {
  show(): void
  hide(): void
  onClick(cb: () => void): void
  offClick(cb: () => void): void
}

interface TelegramHaptics {
  impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void
  notificationOccurred(type: 'error' | 'success' | 'warning'): void
  selectionChanged(): void
}

export interface TelegramWebApp {
  initData: string
  initDataUnsafe: { start_param?: string }
  platform: string
  ready(): void
  expand(): void
  setHeaderColor(color: string): void
  setBackgroundColor(color: string): void
  setBottomBarColor?(color: string): void
  openTelegramLink(url: string): void
  BackButton: TelegramBackButton
  HapticFeedback: TelegramHaptics
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

export function webApp(): TelegramWebApp | undefined {
  const app = window.Telegram?.WebApp
  // The script also defines WebApp outside Telegram, with empty initData and platform "unknown"
  return app && app.platform !== 'unknown' ? app : undefined
}

export function isInTelegram(): boolean {
  return webApp() !== undefined
}

/** Raw initData for the backend to verify (US-01). Never log it. */
export function initDataRaw(): string | undefined {
  return webApp()?.initData || undefined
}

/** `startapp` parameter, e.g. an invite code from `t.me/<bot>?startapp=<code>`. */
export function startParam(): string | undefined {
  return webApp()?.initDataUnsafe.start_param || undefined
}

export function signalReady(): void {
  const app = webApp()
  app?.ready()
  app?.expand()
}

export function paintChrome(color: string): void {
  const app = webApp()
  if (!app) return
  app.setHeaderColor(color)
  app.setBackgroundColor(color)
  app.setBottomBarColor?.(color)
}

export function haptic(kind: 'tap' | 'success' | 'error'): void {
  const h = webApp()?.HapticFeedback
  if (!h) return
  if (kind === 'tap') h.impactOccurred('light')
  else h.notificationOccurred(kind)
}

export function shareLink(url: string, text: string): void {
  const share = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`
  const app = webApp()
  if (app) app.openTelegramLink(share)
  else window.open(share, '_blank', 'noopener')
}
