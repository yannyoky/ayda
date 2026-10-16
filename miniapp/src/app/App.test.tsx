import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from './App'

describe('App shell', () => {
  it('renders the Today screen with the bottom navigation', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'Сегодня' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Основное меню' })
    for (const name of ['Сегодня', 'Лента', 'Друзья', 'Профиль']) {
      expect(nav.querySelector(`a[aria-label="${name}"]`)).not.toBeNull()
    }
  })

  it('navigates between tabs', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('link', { name: 'Лента' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Лента' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Лента' })).toHaveAttribute('aria-current', 'page')
  })

  it('uses Graphite by default and switches to Plum (US-03)', async () => {
    const user = userEvent.setup()
    render(<App initialPath="/profile" />)
    expect(document.documentElement.dataset.theme).toBe('graphite')
    await user.click(screen.getByRole('radio', { name: 'Слива' }))
    expect(document.documentElement.dataset.theme).toBe('plum')
  })
})
