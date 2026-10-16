import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { useAcceptInvite } from '../../api/queries'
import { t } from '../../i18n'
import { haptic, startParam } from '../../telegram/webapp'
import { Icon } from '../../ui/Icon'

function isChatParam(code: string | undefined): boolean {
  return /^c[0-9a-f]{32}$/.test(code ?? '')
}

/** Accepts a `startapp` invite code once per launch and says how it went (US-12). */
export function InviteBanner() {
  const accept = useAcceptInvite()
  const started = useRef(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    const code = startParam()
    // Bot buttons open the app with `r-morning` / `r-evening` (reminders) or `c<hex>` (a chat);
    // those are not invite codes, which are 12 characters long
    if (code?.startsWith('r-') || isChatParam(code)) return
    if (started.current || !code) return
    started.current = true
    accept.mutate(code, { onSuccess: () => haptic('success') })
  }, [accept])

  if (dismissed || accept.isIdle || accept.isPending) return null
  let text: string = t.friends.inviteNotFound
  if (accept.isSuccess) text = t.friends.accepted(accept.data.first_name)
  else if (accept.error instanceof ApiError && accept.error.status === 409) text = t.friends.inviteOwn
  else if (accept.error instanceof ApiError && accept.error.status === 410) text = t.friends.inviteExpired

  return (
    <div role="status" className="flex items-center gap-3 rounded-card bg-plate p-3 pl-4 text-on-plate">
      <span className="flex-1 text-[15px] font-bold">{text}</span>
      <button type="button" aria-label={t.friends.dismiss} onClick={() => setDismissed(true)} className="flex size-10 items-center justify-center rounded-tile bg-plate-2">
        <Icon name="close" size={18} />
      </button>
    </div>
  )
}
