import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { db } from '../mocks/db'
import { renderApp } from '../test/render'

describe('Feed (US-13, US-14)', () => {
  it('shows proofs with photos and routines without details', async () => {
    renderApp('/feed')
    const proof = await screen.findByRole('article', { name: /Лена: Пробежка 5 км/ })
    expect(within(proof).getByRole('img', { name: 'Фото 1 из 1' })).toBeInTheDocument()
    const routine = screen.getByRole('article', { name: 'Дима: Рутина' })
    expect(within(routine).getByText(/Квест скрыт/)).toBeInTheDocument()
    expect(within(routine).queryByRole('img')).not.toBeInTheDocument()
  })

  it('likes and unlikes a post once per person', async () => {
    const user = userEvent.setup()
    renderApp('/feed')
    const proof = await screen.findByRole('article', { name: /Лена/ })
    await user.click(within(proof).getByRole('button', { name: 'Нравится, 14' }))
    expect(await within(proof).findByRole('button', { name: 'Убрать лайк, 15' })).toHaveAttribute('aria-pressed', 'true')
    expect(db.posts[0]!.like_count).toBe(15)
    await user.click(within(proof).getByRole('button', { name: 'Убрать лайк, 15' }))
    expect(await within(proof).findByRole('button', { name: 'Нравится, 14' })).toBeInTheDocument()
  })

  it('adds and deletes an own comment', async () => {
    const user = userEvent.setup()
    renderApp('/feed')
    const proof = await screen.findByRole('article', { name: /Лена/ })
    await user.click(within(proof).getByRole('button', { name: 'Комментарии, 1' }))
    const sheet = screen.getByRole('dialog', { name: 'Комментарии' })
    expect(await within(sheet).findByText('Огонь! Завтра со мной?')).toBeInTheDocument()
    // Someone else's comment on someone else's post cannot be deleted
    expect(within(sheet).queryByRole('button', { name: 'Удалить комментарий' })).not.toBeInTheDocument()

    await user.type(within(sheet).getByRole('textbox', { name: 'Написать комментарий' }), 'Красота!')
    await user.click(within(sheet).getByRole('button', { name: 'Отправить' }))
    expect(await within(sheet).findByText('Красота!')).toBeInTheDocument()
    expect(within(proof).getByRole('button', { name: 'Комментарии, 2' })).toBeInTheDocument()

    await user.click(within(sheet).getByRole('button', { name: 'Удалить комментарий' }))
    expect(await within(proof).findByRole('button', { name: 'Комментарии, 1' })).toBeInTheDocument()
  })

  it('deletes an own post after a confirmation', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const q = db.addOwn({ title: 'Пробежка у моря', category: 'sport', duration_min: 30 })
    db.complete(db.quest(q.id)!, { visibility: 'friends', media_ids: ['00000000-0000-4000-8000-000000000002'] })
    renderApp('/feed')
    const mine = await screen.findByRole('article', { name: 'Ты: Пробежка у моря' })
    await user.click(within(mine).getByRole('button', { name: 'Удалить пост' }))
    expect(screen.queryByRole('article', { name: 'Ты: Пробежка у моря' })).not.toBeInTheDocument()
    expect(db.posts.some((p) => p.quest_title === 'Пробежка у моря')).toBe(false)
  })
})
