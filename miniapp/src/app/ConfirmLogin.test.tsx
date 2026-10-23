import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderApp } from '../test/render'
import { server } from '../test/server'
import { fakeTelegram } from '../test/telegram'

describe('confirming a native app sign-in (ADR 0009)', () => {
  it('confirms with initData and does not sign in to the Mini App', async () => {
    const app = fakeTelegram('query_id=AAE&user=%7B%7D&hash=abc', 'login_Abc123')
    const sent: unknown[] = []
    const urls: string[] = []
    server.events.on('request:start', async ({ request }) => {
      urls.push(new URL(request.url).pathname)
      if (request.url.endsWith('/approve')) sent.push(await request.clone().json())
    })
    const user = userEvent.setup()
    renderApp()
    await user.click(await screen.findByRole('button', { name: 'Подтвердить вход' }))
    expect(await screen.findByRole('heading', { name: 'Готово' })).toBeInTheDocument()
    expect(sent).toEqual([{ init_data: 'query_id=AAE&user=%7B%7D&hash=abc', code: 'Abc123' }])
    expect(urls).not.toContain('/api/v1/auth/telegram')

    await user.click(screen.getByRole('button', { name: 'Закрыть' }))
    expect(app.close).toHaveBeenCalled()
    server.events.removeAllListeners()
  })

  it('tells that an old link expired', async () => {
    fakeTelegram('query_id=AAE&user=%7B%7D&hash=abc', 'login_expired')
    const user = userEvent.setup()
    renderApp()
    await user.click(await screen.findByRole('button', { name: 'Подтвердить вход' }))
    expect(await screen.findByRole('heading', { name: 'Ссылка устарела' })).toBeInTheDocument()
  })
})
