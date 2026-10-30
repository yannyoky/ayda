import { useMutation } from '@tanstack/react-query'
import { api, unwrap } from '../api/client'
import { t } from '../i18n'
import { closeApp, haptic } from '../telegram/webapp'
import { FullScreen, PrimaryButton } from '../ui/states'

/** "It was not me" from the bot's notice about a sign-in on another device: ends every session
 * of the account, this one included (audit V5). */
export function SignOutEverywhereScreen() {
  const signOut = useMutation({
    mutationFn: () => unwrap(api.POST('/auth/sign-out-everywhere')),
    onSuccess: () => haptic('success'),
    onError: () => haptic('error'),
  })

  if (signOut.isSuccess) {
    return (
      <FullScreen
        title={t.signOutEverywhere.done}
        text={t.signOutEverywhere.doneText}
        action={<PrimaryButton onClick={closeApp}>{t.signOutEverywhere.close}</PrimaryButton>}
      />
    )
  }
  return (
    <FullScreen
      title={t.signOutEverywhere.title}
      text={signOut.isError ? t.signOutEverywhere.failedText : t.signOutEverywhere.text}
      action={
        <PrimaryButton disabled={signOut.isPending} onClick={() => signOut.mutate()}>
          {signOut.isError ? t.common.retry : t.signOutEverywhere.confirm}
        </PrimaryButton>
      }
    />
  )
}
