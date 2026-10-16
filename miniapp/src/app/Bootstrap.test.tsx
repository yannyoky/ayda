import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderApp } from '../test/render'
import { fakeTelegram } from '../test/telegram'

describe('sign-in with Telegram (US-01)', () => {
  it('sends the raw initData to the backend', async () => {
    fakeTelegram('query_id=AAE&user=%7B%7D&hash=abc')
    let sent: unknown
    const unauthorized: string[] = []
    server.events.on('request:start', async ({ request }) => {
      if (request.url.endsWith('/auth/telegram')) sent = await request.clone().json()
    })
    server.events.on('response:mocked', ({ request, response }) => {
      if (response.status === 401) unauthorized.push(request.url)
    })
    renderApp()
    expect(await screen.findByRole('heading', { level: 1, name: 'Привет, Саша' })).toBeInTheDocument()
    expect(sent).toEqual({ init_data: 'query_id=AAE&user=%7B%7D&hash=abc' })
    // Nothing is requested before the session exists
    expect(unauthorized).toEqual([])
    server.events.removeAllListeners()
  })

  it('explains a rejected signature and offers a retry', async () => {
    fakeTelegram('invalid')
    renderApp()
    expect(await screen.findByRole('heading', { name: 'Не получилось войти' })).toBeInTheDocument()
    expect(screen.getByText(/Telegram не подтвердил вход/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeEnabled()
  })

  it('signs in again when the token expires', async () => {
    let calls = 0
    server.use(
      http.get('*/api/v1/me', () => {
        calls += 1
        return calls === 1
          ? HttpResponse.json({ type: 'about:blank', title: 'expired', status: 401 }, { status: 401 })
          : undefined
      }),
    )
    renderApp('/profile')
    expect(await screen.findByRole('heading', { level: 1, name: 'Профиль' })).toBeInTheDocument()
  })
})
