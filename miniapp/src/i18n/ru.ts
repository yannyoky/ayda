// Russian UI strings. Every user-facing string lives here (PRD: strings in translation files).
export const ru = {
  appName: 'Ayda',
  nav: {
    label: 'Основное меню',
    today: 'Сегодня',
    feed: 'Лента',
    friends: 'Друзья',
    profile: 'Профиль',
  },
  today: {
    greeting: (name: string) => `Привет, ${name}`,
  },
  feed: {
    title: 'Лента',
  },
  friends: {
    title: 'Друзья',
  },
  profile: {
    title: 'Профиль',
    theme: 'Тема',
    themes: { graphite: 'Графит', plum: 'Слива' },
  },
  common: {
    loading: 'Загружаем…',
    retry: 'Повторить',
    errorGeneric: 'Что-то пошло не так',
  },
} as const

export type Strings = typeof ru
