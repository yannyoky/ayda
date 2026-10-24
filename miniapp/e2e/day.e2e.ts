import { expect, test } from '@playwright/test'
import { openAsTelegramUser } from './telegram'

// The core loop on a real backend (no LLM, so the pool comes from code):
// Telegram sign-in → consent → onboarding → check-in → pick a quest → complete it → feed.
test('a new user gets quests for the day, completes one and sees it in the feed', async ({ page }) => {
  // A fresh Telegram id per run, so the scenario always starts as a new user
  await openAsTelegramUser(page, { id: 100_000_000 + (Date.now() % 100_000_000), first_name: 'Тест' })

  await test.step('consent', async () => {
    await expect(page.getByRole('heading', { name: 'Пара слов о данных' })).toBeVisible()
    await page.getByRole('checkbox', { name: /Согласен/ }).check()
    await page.getByRole('button', { name: 'Продолжить' }).click()
  })

  await test.step('onboarding: city, then skip the optional steps', async () => {
    await expect(page.getByRole('heading', { name: 'Где ты живёшь?' })).toBeVisible()
    await page.getByRole('searchbox', { name: 'Город' }).fill('Калинингр')
    await page.getByRole('button', { name: /^Калининград/ }).first().click()
    await page.getByRole('button', { name: /Дальше/ }).click()
    for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Пропустить' }).click()
    await expect(page.getByRole('heading', { name: 'Выбери тему' })).toBeVisible()
    await page.getByRole('button', { name: 'Начать' }).click()
  })

  await test.step('check-in builds a pool with the own plan and catalog quests', async () => {
    await expect(page.getByRole('banner')).toContainText('Калининград')
    await page.getByRole('textbox', { name: 'Какой у тебя день?' }).fill('Работа до 18, вечером свободен')
    await page.getByRole('button', { name: 'Собрать квесты' }).click()
    await expect(page.getByRole('heading', { name: 'Квесты на сегодня' })).toBeVisible()
    const cards = page.getByRole('main').getByRole('listitem')
    await expect(cards.filter({ hasText: 'Работа до 18' })).toHaveCount(1)
    expect(await cards.count()).toBeGreaterThanOrEqual(5)
  })

  let title = ''
  await test.step('take a catalog quest', async () => {
    const card = page.getByRole('main').getByRole('listitem').filter({ hasNotText: 'из твоего плана' }).first()
    await card.getByRole('button').first().click()
    await page.getByRole('button', { name: /Взять 1 квест/ }).click()
    await expect(page.getByRole('region', { name: 'Квесты дня' }).getByRole('listitem')).toHaveCount(1)
  })

  await test.step('complete it with a text proof', async () => {
    const done = page.getByRole('button', { name: /^Готово:/ })
    title = ((await done.getAttribute('aria-label')) ?? '').replace(/^Готово: /, '')
    expect(title).not.toBe('')
    await done.click()
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
    await page.getByRole('textbox', { name: 'Подпись' }).fill('Получилось с первого раза')
    await page.getByRole('button', { name: 'Отметить' }).click()
    await expect(page.getByRole('status')).toContainText('Засчитано!')
  })

  await test.step('the proof is in the feed', async () => {
    await page.getByRole('link', { name: 'Открыть ленту' }).click()
    const post = page.getByRole('article', { name: `Ты: ${title}` })
    await expect(post).toBeVisible()
    await expect(post).toContainText('Получилось с первого раза')
  })

  await test.step('Today shows the quest as done', async () => {
    await page.getByRole('link', { name: 'Сегодня' }).click()
    const today = page.getByRole('region', { name: 'Квесты дня' })
    await expect(today).toContainText('очки за 1 из 5')
    await expect(today.getByRole('button', { name: /^Готово:/ })).toHaveCount(0)
  })
})
