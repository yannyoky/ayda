import { useState } from 'react'
import { useAcceptConsent } from '../../api/queries'
import { t } from '../../i18n'
import { InlineError, PrimaryButton } from '../../ui/states'
import { ConsentText } from './ConsentText'

/** Consent to personal data processing, shown before anything else (152-FZ). */
export function ConsentScreen({ version }: { version: string }) {
  const [agreed, setAgreed] = useState(false)
  const accept = useAcceptConsent()
  return (
    <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-4 px-4 pt-[max(24px,env(safe-area-inset-top))] pb-8">
      <h1 className="m-0 px-1 font-display text-[26px] font-bold tracking-[-0.5px]">{t.consent.title}</h1>
      <ConsentText />
      <label className="flex items-start gap-3 rounded-card bg-surface p-4 text-[15px] font-bold">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-[var(--color-ink)]" />
        {t.consent.accept}
      </label>
      {accept.isError && <InlineError />}
      <PrimaryButton disabled={!agreed || accept.isPending} onClick={() => accept.mutate(version)} className="mt-auto">
        {t.consent.continue}
      </PrimaryButton>
    </main>
  )
}
