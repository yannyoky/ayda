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

/** What to say when ticking an item or handing a part off fails. */
export function partErrorText(error: Error): string {
  if (!(error instanceof ApiError)) return t.coop.plan.errors.generic
  const type = error.problem?.type ?? ''
  if (type.endsWith('/not-part-assignee')) return t.coop.plan.errors.notAssignee
  if (type.endsWith('/part-locked')) return t.coop.plan.errors.locked
  if (type.endsWith('/part-done')) return t.coop.plan.errors.done
  if (type.endsWith('/handoff-pending')) return t.coop.plan.errors.pending
  if (type.endsWith('/coop-full')) return t.coop.plan.errors.full
  if (error.status === 404) return t.coop.notFound
  return error.problem?.detail ?? t.coop.plan.errors.generic
}
