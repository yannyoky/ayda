import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { db } from '../mocks/db'
import { renderApp } from '../test/render'
import { fakeTelegram } from '../test/telegram'

describe('Friends ladder (US-16)', () => {
  it('ranks friends by weekly points with me highlighted', async () => {
    renderApp('/friends')
    const ladder = await screen.findByRole('list', { name: 'Рейтинг друзей' })
    const podium = within(ladder).getAllByRole('listitem')
    expect(podium.map((li) => li.getAttribute('aria-label'))).toEqual(['2 место: Дима, 265', '1 место: Лена, 410', '3 место: Костя, 190'])
    expect(screen.getByRole('listitem', { name: '4 место: Ты, 185' })).toBeInTheDocument()
  })

  it('switches to the previous week', async () => {
    const user = userEvent.setup()
    renderApp('/friends')
    await screen.findByRole('listitem', { name: '1 место: Лена, 410' })
    await user.click(screen.getByText('Прошлая'))
    expect(await screen.findByRole('listitem', { name: '1 место: Лена, 330' })).toBeInTheDocument()
    expect(screen.getByRole('listitem', { name: '3 место: Ты, 260' })).toBeInTheDocument()
  })

  it('says so when there are no friends yet', async () => {
    db.reset({ onboarded: true, poolDelayMs: 0, withFriends: false })
    renderApp('/friends')
    expect(await screen.findByText(/Позови друзей/)).toBeInTheDocument()
  })
})

describe('Friends and invites (US-12)', () => {
  it('shares an invite link through Telegram', async () => {
    const tg = fakeTelegram('query_id=AAE&user=%7B%7D&hash=abc')
    const user = userEvent.setup()
    renderApp('/friends')
    await user.click(await screen.findByRole('button', { name: 'Позвать друга' }))
    expect(await screen.findByRole('status')).toBeInTheDocument()
    expect(tg.openTelegramLink).toHaveBeenCalledWith(expect.stringMatching(/^https:\/\/t\.me\/share\/url\?url=https%3A%2F%2Ft\.me%2Fayda_quest_bot%3Fstartapp%3D/))
  })

  it('removes a friend after confirmation', async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderApp('/friends')
    await user.click(await screen.findByRole('button', { name: 'Убрать Костя из друзей' }))
    expect(confirm).toHaveBeenCalled()
    await vi.waitFor(() => expect(screen.queryByRole('button', { name: 'Убрать Костя из друзей' })).not.toBeInTheDocument())
    expect(db.friends.map((f) => f.first_name)).not.toContain('Костя')
    confirm.mockRestore()
  })

  it('accepts an invite from the launch link', async () => {
    fakeTelegram('query_id=AAE&user=%7B%7D&hash=abc', 'welcome-invite-code')
    renderApp()
    expect(await screen.findByRole('status')).toHaveTextContent('Оля теперь у тебя в друзьях')
    expect(db.friends.map((f) => f.first_name)).toContain('Оля')
  })

  it('explains an expired invite', async () => {
    db.invites.set('old-code', { inviterId: null, expiresAt: '2020-01-01T00:00:00Z' })
    fakeTelegram('query_id=AAE&user=%7B%7D&hash=abc', 'old-code')
    renderApp()
    expect(await screen.findByRole('status')).toHaveTextContent(/истекл/)
  })
})
