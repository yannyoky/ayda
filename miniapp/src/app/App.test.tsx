import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { db } from '../mocks/db'
import { renderApp } from '../test/render'

describe('App shell', () => {
  it('renders the Today screen with the bottom navigation', async () => {
    renderApp()
    expect(await screen.findByRole('heading', { name: 'Начнём день' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Основное меню' })
    for (const name of ['Сегодня', 'Лента', 'Друзья', 'Профиль']) {
      expect(nav.querySelector(`a[aria-label="${name}"]`)).not.toBeNull()
    }
  })

  it('navigates between tabs', async () => {
    const user = userEvent.setup()
    renderApp()
    await user.click(await screen.findByRole('link', { name: 'Лента' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Лента' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Лента' })).toHaveAttribute('aria-current', 'page')
  })

  it('applies the profile theme and saves a new one (US-03)', async () => {
    const user = userEvent.setup()
    renderApp('/profile')
    await screen.findByRole('radio', { name: 'Слива' })
    expect(document.documentElement.dataset.theme).toBe('graphite')
    await user.click(screen.getByRole('radio', { name: 'Слива' }))
    expect(document.documentElement.dataset.theme).toBe('plum')
    expect(db.me.theme).toBe('plum')
  })
})
