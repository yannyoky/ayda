import { useEffect } from 'react'
import { webApp } from './webapp'

/** Shows Telegram's native back button while the calling screen is mounted. */
export function useBackButton(onBack: () => void): void {
  useEffect(() => {
    const button = webApp()?.BackButton
    if (!button) return
    button.onClick(onBack)
    button.show()
    return () => {
      button.offClick(onBack)
      button.hide()
    }
  }, [onBack])
}
