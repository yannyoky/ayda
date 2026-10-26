import { openExternal } from '../../telegram/webapp'

/** Served by Caddy from miniapp/public (docs/privacy.md is the source). */
export const PRIVACY_PATH = '/privacy.html'

/** Opens the privacy policy page outside the app. */
export function openPrivacyPolicy() {
  openExternal(new URL(PRIVACY_PATH, window.location.origin).href)
}
