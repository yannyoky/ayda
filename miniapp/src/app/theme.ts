import { useEffect } from 'react'
import type { Schemas } from '../api/client'
import { paintChrome } from '../telegram/webapp'

export type Theme = Schemas['Theme']

export const DEFAULT_THEME: Theme = 'graphite'

const BACKGROUND: Record<Theme, string> = { graphite: '#E9E9E7', plum: '#F1E9E4' }

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  paintChrome(BACKGROUND[theme])
}

/** Keeps <html data-theme> and the Telegram chrome in sync with the profile theme (US-03). */
export function useApplyTheme(theme: Theme | undefined): void {
  useEffect(() => applyTheme(theme ?? DEFAULT_THEME), [theme])
}
