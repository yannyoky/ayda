import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { setAccessToken } from '../api/client'
import { db } from '../mocks/db'
import { server } from './server'

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
beforeEach(() => db.reset({ onboarded: true, poolDelayMs: 0 }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  setAccessToken(undefined)
  delete window.Telegram
  delete document.documentElement.dataset.theme
})
afterAll(() => server.close())
