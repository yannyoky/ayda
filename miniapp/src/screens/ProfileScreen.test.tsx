import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { db } from '../mocks/db'
import { renderApp } from '../test/render'

describe('Profile', () => {
  it('changes the city and reminders after onboarding (US-02)', async () => {
    const user = userEvent.setup()
    renderApp('/profile')
    await screen.findByText('Калининград, Калининградская область')

    const [cityButton] = screen.getAllByRole('button', { name: 'Изменить' })
    await user.click(cityButton!)
    await user.type(screen.getByRole('searchbox', { name: 'Город' }), 'Каз')
    await user.click(await screen.findByRole('button', { name: /Казань/ }))
    expect(await screen.findByText('Казань, Республика Татарстан')).toBeInTheDocument()
    expect(db.me.timezone).toBe('Europe/Moscow')

    const reminders = screen.getAllByRole('button', { name: 'Изменить' }).at(-1)!
    await user.click(reminders)
    await user.click(screen.getByRole('switch', { name: 'Утром' }))
    expect(await screen.findByText(/утром выключено/)).toBeInTheDocument()
    expect(db.me.reminders.morning_at).toBeNull()
  })

  it('requests account deletion after a confirmation (152-FZ)', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderApp('/profile')
    await user.click(await screen.findByRole('button', { name: 'Удалить аккаунт' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Аккаунт поставлен на удаление')
    expect(db.deletionRequested).toBe(true)
  })
})
