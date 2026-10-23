import { useMutation } from '@tanstack/react-query'
import { api, ApiError, unwrap } from '../api/client'
import { t } from '../i18n'
import { haptic, initDataRaw, returnToNativeApp } from '../telegram/webapp'
import { FullScreen, PrimaryButton } from '../ui/states'

/** Confirms a sign-in started in the native app (ADR 0009). The Mini App's initData proves the
 * Telegram user, so this works even when the bot gets no updates. */
export function ConfirmLogin({ code }: { code: string }) {
  const approve = useMutation({
    mutationFn: () =>
      unwrap(api.POST('/auth/telegram/login-requests/approve', { body: { init_data: initDataRaw() ?? '', code } })),
    onSuccess: () => haptic('success'),
    onError: () => haptic('error'),
  })

  if (approve.isSuccess) {
    return <FullScreen title={t.nativeLogin.done} text={t.nativeLogin.doneText} action={<PrimaryButton onClick={returnToNativeApp}>{t.nativeLogin.close}</PrimaryButton>} />
  }
  const expired = approve.error instanceof ApiError && approve.error.status === 404
  if (expired) return <FullScreen title={t.nativeLogin.expired} text={t.nativeLogin.expiredText} />
  return (
    <FullScreen
      title={t.nativeLogin.title}
      text={approve.isError ? t.nativeLogin.failedText : t.nativeLogin.text}
      action={
        <PrimaryButton disabled={approve.isPending} onClick={() => approve.mutate()}>
          {approve.isError ? t.common.retry : t.nativeLogin.confirm}
        </PrimaryButton>
      }
    />
  )
}
