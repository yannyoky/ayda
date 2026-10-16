import createClient, { type Middleware } from 'openapi-fetch'
import type { components, paths } from './schema.gen'

export type Schemas = components['schemas']
export type Problem = Schemas['Problem']

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

// Kept in memory only: every launch from Telegram signs in again with fresh initData
let accessToken: string | undefined

export function setAccessToken(token: string | undefined): void {
  accessToken = token
}

export function hasAccessToken(): boolean {
  return accessToken !== undefined
}

const auth: Middleware = {
  onRequest({ request }) {
    if (accessToken) request.headers.set('Authorization', `Bearer ${accessToken}`)
    return request
  },
}

export const api = createClient<paths>({
  baseUrl: new URL(API_BASE_URL, window.location.origin).href.replace(/\/$/, ''),
  // Resolve fetch per call so test and dev mocks that patch it are honoured
  fetch: (request) => globalThis.fetch(request),
})
api.use(auth)

/** Error thrown by `unwrap` with the RFC 9457 problem from the server. */
export class ApiError extends Error {
  readonly status: number
  readonly problem: Problem | undefined

  constructor(status: number, problem: Problem | undefined) {
    super(problem?.title ?? `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.problem = problem
  }
}

/** Turns an openapi-fetch result into data or a thrown ApiError, for TanStack Query. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call
  if (error !== undefined || !response.ok) {
    throw new ApiError(response.status, isProblem(error) ? error : undefined)
  }
  return data as T
}

function isProblem(x: unknown): x is Problem {
  return typeof x === 'object' && x !== null && 'status' in x && 'title' in x
}
