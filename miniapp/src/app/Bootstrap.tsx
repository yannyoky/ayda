import { useState, type ReactNode } from 'react'
import { ApiError } from '../api/client'
import { NotInTelegramError, useMe, useSession } from '../api/queries'
import { ConsentScreen } from '../features/onboarding/ConsentScreen'
import { Onboarding } from '../features/onboarding/Onboarding'
import { t } from '../i18n'
import { useRealtime } from '../realtime/realtime'
import { FullScreen, PrimaryButton, Splash } from '../ui/states'
import { nativeLoginCode } from '../telegram/webapp'
import { ConfirmLogin } from './ConfirmLogin'
import { useApplyTheme } from './theme'

/** Signs in with Telegram (US-01), then asks for consent and onboarding before the app itself.
 * Opened from the native app's sign-in link, it only confirms that sign-in. */
export function Bootstrap({ children }: { children: ReactNode }) {
  const [loginCode] = useState(nativeLoginCode)
  if (loginCode) return <ConfirmLogin code={loginCode} />
  return <SignedIn>{children}</SignedIn>
}

function SignedIn({ children }: { children: ReactNode }) {
  const session = useSession()
  const me = useMe({ signedIn: session.isSuccess })
  const [retrying, setRetrying] = useState(false)
  useApplyTheme(me.data?.theme)
  useRealtime(Boolean(me.data?.onboarded && !me.data.consent_required))

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
