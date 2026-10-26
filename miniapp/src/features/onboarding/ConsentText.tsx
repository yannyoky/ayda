import { t } from '../../i18n'
import { openPrivacyPolicy } from './privacy'

/** The consent text itself, shared by the consent screen and the profile. */
export function ConsentText() {
  return (
    <>
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
      <p className="m-0 px-1 text-[13px] font-medium text-muted">
        {t.consent.policy}{' '}
        <button type="button" onClick={openPrivacyPolicy} className="cursor-pointer border-0 bg-transparent p-0 font-bold text-ink underline">
          {t.consent.policyLink}
        </button>
      </p>
    </>
  )
}
