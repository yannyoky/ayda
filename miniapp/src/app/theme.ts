import { createContext, useContext } from 'react'
import type { Schemas } from '../api/client'
import { paintChrome } from '../telegram/webapp'

export type Theme = Schemas['Theme']

export const DEFAULT_THEME: Theme = 'graphite'

const BACKGROUND: Record<Theme, string> = { graphite: '#E9E9E7', plum: '#F1E9E4' }

export interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
}

export const ThemeContext = createContext<ThemeState | null>(null)

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  paintChrome(BACKGROUND[theme])
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme outside ThemeProvider')
  return ctx
}
