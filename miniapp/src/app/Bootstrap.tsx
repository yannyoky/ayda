import { useState, type ReactNode } from 'react'
import { ApiError } from '../api/client'
import { NotInTelegramError, useMe, useSession } from '../api/queries'
import { ConsentScreen } from '../features/onboarding/ConsentScreen'
import { Onboarding } from '../features/onboarding/Onboarding'
import { t } from '../i18n'
import { FullScreen, PrimaryButton, Splash } from '../ui/states'
import { useApplyTheme } from './theme'

/** Signs in with Telegram (US-01), then asks for consent and onboarding before the app itself. */
export function Bootstrap({ children }: { children: ReactNode }) {
  const session = useSession()
  const me = useMe()
  const [retrying, setRetrying] = useState(false)
  useApplyTheme(me.data?.theme)

  if (session.isPending) return <Splash />
  if (session.isError) {
    if (session.error instanceof NotInTelegramError) {
      return <FullScreen title={t.launch.openInTelegram} text={t.launch.openInTelegramText} />
    }
    const unauthorized = session.error instanceof ApiError && session.error.status === 401
    return (
      <FullScreen
        title={t.launch.signInFailed}
        text={unauthorized ? t.launch.signInRejected : t.launch.signInFailedText}
        action={
          <PrimaryButton
            disabled={retrying}
            onClick={() => {
              setRetrying(true)
              void session.refetch().finally(() => setRetrying(false))
            }}
          >
            {t.common.retry}
          </PrimaryButton>
        }
      />
    )
  }
  if (!me.data) return <Splash />
  if (me.data.consent_required) return <ConsentScreen version={me.data.consent_required} />
  if (!me.data.onboarded) return <Onboarding />
  return <>{children}</>
}
