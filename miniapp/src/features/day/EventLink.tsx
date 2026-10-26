import type { Schemas } from '../../api/client'
import { t } from '../../i18n'
import { openExternal } from '../../telegram/webapp'
import { Icon } from '../../ui/Icon'

const styles = {
  card: 'mx-2 mb-2 flex h-11 items-center justify-center gap-1.5 rounded-field bg-ink/6 text-xs font-extrabold',
  sheet: 'press flex h-12 items-center justify-center gap-2 rounded-field bg-surface text-sm font-extrabold',
  inline: 'flex items-center gap-1 self-start py-0.5 text-xs font-extrabold underline underline-offset-2',
}

/** Opens the event page at its source in the external browser (US-19). */
export function EventLink({ event, title, variant }: { event: Schemas['EventInfo']; title: string; variant: keyof typeof styles }) {
  const source = t.event.sources[event.source]
  return (
    <button type="button" aria-label={t.event.openFor(title, source)} onClick={() => openExternal(event.url)} className={styles[variant]}>
      <Icon name="external" size={14} strokeWidth={2.2} />
      {source}
    </button>
  )
}
