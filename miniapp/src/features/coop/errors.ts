import { ApiError } from '../../api/client'
import { t } from '../../i18n'

/** What to say when accepting or declining a co-op invitation fails. */
export function answerErrorText(error: Error): string {
  if (!(error instanceof ApiError)) return error.message
  if (error.status === 410) return t.coop.over
  if (error.status === 404) return t.coop.notFound
  if (error.status === 409) return error.problem?.type.endsWith('/daily-limit-reached') ? t.coop.limit : t.coop.answered
  return error.problem?.detail ?? error.message
}
