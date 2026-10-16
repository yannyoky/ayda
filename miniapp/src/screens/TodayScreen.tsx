import { formatDayTitle, t } from '../i18n'
import { ScreenHeader } from '../ui/primitives'

export function TodayScreen() {
  return <ScreenHeader eyebrow={formatDayTitle(new Date())} title={t.nav.today} />
}
