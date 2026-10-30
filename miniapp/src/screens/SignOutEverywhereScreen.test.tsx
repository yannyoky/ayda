import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { launchPath } from '../app/launch'
import { renderApp } from '../test/render'
import { server } from '../test/server'
import { fakeTelegram } from '../test/telegram'

describe('sign out everywhere (audit V5)', () => {
  it('opens from the bot notice and ends every session', async () => {
    const app = fakeTelegram('query_id=AAE&user=%7B%7D&hash=abc', 'signout')
    expect(launchPath()).toBe('/signout')
    const urls: string[] = []
    server.events.on('request:start', ({ request }) => {
      if (request.method === 'POST') urls.push(new URL(request.url).pathname)
    })
    const user = userEvent.setup()
    renderApp(launchPath())
    await user.click(await screen.findByRole('button', { name: 'Выйти везде' }))
    expect(await screen.findByRole('heading', { name: 'Готово' })).toBeInTheDocument()
    expect(urls).toContain('/api/v1/auth/sign-out-everywhere')

    await user.click(screen.getByRole('button', { name: 'Закрыть' }))
    expect(app.close).toHaveBeenCalled()
    server.events.removeAllListeners()
  })
})
