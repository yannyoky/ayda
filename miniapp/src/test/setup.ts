import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { setAccessToken } from '../api/client'
import { db } from '../mocks/db'
import { server } from './server'

// jsdom 30's Blob/File has no stream(), which Node's fetch needs to send one as a body
if (typeof Blob.prototype.stream !== 'function') {
  Blob.prototype.stream = function stream(this: Blob) {
    return new ReadableStream({
      start: async (controller) => {
        controller.enqueue(new Uint8Array(await this.arrayBuffer()))
        controller.close()
      },
    })
  }
}

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
beforeEach(() => db.reset({ onboarded: true, poolDelayMs: 0 }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  setAccessToken(undefined)
  delete window.Telegram
  delete document.documentElement.dataset.theme
})
afterAll(() => server.close())
