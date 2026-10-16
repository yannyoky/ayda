import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { applyTheme, DEFAULT_THEME, ThemeContext, type Theme } from './theme'

export function ThemeProvider({ initial = DEFAULT_THEME, children }: { initial?: Theme; children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(initial)

  useEffect(() => applyTheme(theme), [theme])

  const setTheme = useCallback((next: Theme) => setThemeState(next), [])
  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
