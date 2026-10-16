import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { db } from '../../mocks/db'
import { renderApp } from '../../test/render'

beforeEach(() => db.reset({ onboarded: false, poolDelayMs: 0 }))

describe('first launch', () => {
  it('asks for consent before anything else', async () => {
    const user = userEvent.setup()
    renderApp()
    const button = await screen.findByRole('button', { name: 'Продолжить' })
    expect(screen.getByText(/внешний сервис ИИ/)).toBeInTheDocument()
    expect(button).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: /Согласен/ }))
    await user.click(button)
    expect(await screen.findByRole('heading', { name: 'Где ты живёшь?' })).toBeInTheDocument()
    expect(db.me.consent_required).toBeNull()
  })

  it('walks through onboarding: city is required, the rest can be skipped (US-02)', async () => {
    const user = userEvent.setup()
    db.me.consent_required = null
    renderApp()

    await screen.findByRole('heading', { name: 'Где ты живёшь?' })
    expect(screen.getByRole('button', { name: /Дальше/ })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Пропустить' })).not.toBeInTheDocument()
    await user.type(screen.getByRole('searchbox', { name: 'Город' }), 'Калин')
    await user.click(await screen.findByRole('button', { name: /Калининград/ }))
    await user.click(await screen.findByRole('button', { name: /Дальше/, pressed: undefined }))
    expect(db.me.city?.name).toBe('Калининград')
    expect(db.me.timezone).toBe('Europe/Kaliningrad')

    await screen.findByRole('heading', { name: 'Чего хочется?' })
    const goals = await screen.findByRole('group', { name: 'Цели' })
    await user.click(within(goals).getByRole('button', { name: 'Больше двигаться' }))
    await user.click(within(goals).getByRole('button', { name: 'Делать свой проект' }))
    await user.click(screen.getByRole('button', { name: /Дальше/ }))
    expect(db.goalCodes).toEqual(['more_movement', 'own_project'])

    await screen.findByRole('heading', { name: 'Свои привычки' })
    await user.type(screen.getByRole('textbox', { name: 'Хочу меньше' }), 'залипать в рилсы')
    await user.click(screen.getByRole('button', { name: 'Добавить: хочу меньше' }))
    expect(await screen.findByText('залипать в рилсы')).toBeInTheDocument()
    expect(db.habits).toMatchObject([{ direction: 'less', text: 'залипать в рилсы' }])
    await user.click(screen.getByRole('button', { name: 'Пропустить' }))

    await screen.findByRole('heading', { name: 'Когда напоминать?' })
    await user.click(screen.getByRole('switch', { name: 'Вечером' }))
    await user.click(screen.getByRole('button', { name: /Дальше/ }))
    expect(db.me.reminders).toEqual({ morning_at: '08:30', evening_at: null })

    await screen.findByRole('heading', { name: 'Выбери тему' })
    await user.click(screen.getByRole('radio', { name: 'Слива' }))
    expect(document.documentElement.dataset.theme).toBe('plum')
    await user.click(screen.getByRole('button', { name: /Начать/ }))

    expect(await screen.findByRole('navigation', { name: 'Основное меню' })).toBeInTheDocument()
    expect(db.me.onboarded).toBe(true)
  })
})
