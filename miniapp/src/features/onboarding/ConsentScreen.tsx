import { useState } from 'react'
import { useAcceptConsent } from '../../api/queries'
import { t } from '../../i18n'
import { InlineError, PrimaryButton } from '../../ui/states'

/** Consent to personal data processing, shown before anything else (152-FZ). */
export function ConsentScreen({ version }: { version: string }) {
  const [agreed, setAgreed] = useState(false)
  const accept = useAcceptConsent()
  return (
    <main className="mx-auto flex min-h-dvh max-w-[480px] flex-col gap-4 px-4 pt-[max(24px,env(safe-area-inset-top))] pb-8">
      <h1 className="m-0 px-1 font-display text-[26px] font-bold tracking-[-0.5px]">{t.consent.title}</h1>
      <section className="flex flex-col gap-3 rounded-card bg-surface p-4 text-[15px] font-medium">
        <p className="m-0">{t.consent.intro}</p>
        <ul className="m-0 flex list-disc flex-col gap-2 pl-5 marker:text-muted">
          {t.consent.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
      <section className="flex flex-col gap-2 rounded-card bg-plate p-4 text-[15px] font-medium text-on-plate">
        <p className="m-0">{t.consent.llm}</p>
        <p className="m-0">{t.consent.storage}</p>
      </section>
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
