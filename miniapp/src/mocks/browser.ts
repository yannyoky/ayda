import { setupWorker } from 'msw/browser'
import { db } from './db'
import { handlers } from './handlers'

export async function startMockApi(): Promise<void> {
  // ?returning=1 starts as an onboarded user with a streak; default is a brand-new user
  const params = new URLSearchParams(window.location.search)
  db.reset({ onboarded: params.has('returning'), assistantDelayMs: 900 })
  await setupWorker(...handlers).start({ onUnhandledFrame: 'bypass', quiet: true })
}
