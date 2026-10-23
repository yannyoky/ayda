// Seed data for the mock API. Shapes follow contracts/openapi.yaml.
import type { Schemas } from '../api/client'

export const CONSENT_VERSION = '2026-10-16'

export const cities: Schemas['City'][] = [
  { id: 1, name: 'Москва', region_name: 'Москва', timezone: 'Europe/Moscow' },
  { id: 2, name: 'Санкт-Петербург', region_name: 'Санкт-Петербург', timezone: 'Europe/Moscow' },
  { id: 3, name: 'Калининград', region_name: 'Калининградская область', timezone: 'Europe/Kaliningrad' },
  { id: 4, name: 'Казань', region_name: 'Республика Татарстан', timezone: 'Europe/Moscow' },
  { id: 5, name: 'Екатеринбург', region_name: 'Свердловская область', timezone: 'Asia/Yekaterinburg' },
  { id: 6, name: 'Новосибирск', region_name: 'Новосибирская область', timezone: 'Asia/Novosibirsk' },
  { id: 7, name: 'Нижний Новгород', region_name: 'Нижегородская область', timezone: 'Europe/Moscow' },
  { id: 8, name: 'Краснодар', region_name: 'Краснодарский край', timezone: 'Europe/Moscow' },
  { id: 9, name: 'Самара', region_name: 'Самарская область', timezone: 'Europe/Samara' },
  { id: 10, name: 'Владивосток', region_name: 'Приморский край', timezone: 'Asia/Vladivostok' },
  { id: 11, name: 'Зеленоградск', region_name: 'Калининградская область', timezone: 'Europe/Kaliningrad' },
]

export const goals: Schemas['Goal'][] = [
  { code: 'more_movement', title: 'Больше двигаться' },
  { code: 'less_screen', title: 'Меньше экранов' },
  { code: 'own_project', title: 'Делать свой проект' },
  { code: 'rest_better', title: 'Нормально отдыхать' },
  { code: 'see_city', title: 'Чаще выбираться в город' },
  { code: 'friends', title: 'Видеться с друзьями' },
  { code: 'learn', title: 'Учиться новому' },
  { code: 'home_food', title: 'Готовить дома' },
]

export interface CatalogQuest {
  title: string
  category: Schemas['Category']
  duration_min: number
  outdoor: boolean
  why: string
  description?: string
}

export const catalog: CatalogQuest[] = [
  { title: 'Прогулка по набережной', category: 'walk', duration_min: 40, outdoor: true, why: 'Вечер свободен, а на улице ясно' },
  { title: 'Час на свой проект', category: 'project', duration_min: 60, outdoor: false, why: 'Ты хотел больше времени на своё' },
  { title: 'Зарядка 15 минут', category: 'sport', duration_min: 15, outdoor: false, why: 'Короткий старт дня' },
  { title: 'Ужин из 5 продуктов', category: 'home', duration_min: 45, outdoor: false, why: 'Готовить дома, а не заказывать' },
  { title: 'Без экранов после 22:00', category: 'rest', duration_min: 60, outdoor: false, why: 'Ты устал, нужен нормальный сон' },
  { title: 'Новая кофейня в центре', category: 'city', duration_min: 30, outdoor: true, why: 'Повод выбраться в город' },
  { title: 'Позвонить другу', category: 'social', duration_min: 20, outdoor: false, why: 'Давно не виделись' },
  { title: '20 страниц книги', category: 'learning', duration_min: 30, outdoor: false, why: 'Учиться понемногу каждый день' },
  { title: 'Пробежка 3 км', category: 'sport', duration_min: 25, outdoor: true, why: 'Больше движения' },
  { title: 'Растяжка перед сном', category: 'rest', duration_min: 10, outdoor: false, why: 'Мягко закрыть день' },
  { title: 'Музей или выставка', category: 'city', duration_min: 90, outdoor: false, why: 'Выходной, можно в город' },
  { title: 'Урок в Duolingo', category: 'learning', duration_min: 15, outdoor: false, why: 'Маленький шаг каждый день' },
  { title: 'Разобрать стол', category: 'home', duration_min: 15, outdoor: false, why: 'Чистое место для работы' },
  { title: 'Тренировка в зале', category: 'sport', duration_min: 60, outdoor: false, why: 'Цель: больше двигаться' },
]

export const friendNames = ['Лена', 'Дима', 'Костя', 'Аня', 'Миша']

export const sampleCaptions = ['Сделано!', 'Тяжело, но кайф', 'Наконец-то', 'Завтра повторю']

/** Local events for event quests (US-19); start times are set when the pool is built. */
export const sampleEvents: (Omit<Schemas['EventInfo'], 'starts_at' | 'ends_at'> & { category: Schemas['Category']; in_hours: number })[] = [
  {
    title: 'Лекция «Как устроено Балтийское море»',
    venue: 'Музей Мирового океана',
    address: 'наб. Петра Великого, 1',
    city: null,
    is_free: true,
    price_min: null,
    url: 'https://example.timepad.ru/event/1/',
    source: 'timepad',
    category: 'learning',
    in_hours: 4,
  },
  {
    title: 'Джаз во дворе',
    venue: 'Дом искусств',
    address: 'ул. Театральная, 1',
    city: 'Зеленоградск',
    is_free: false,
    price_min: 700,
    url: 'https://example.timepad.ru/event/2/',
    source: 'timepad',
    category: 'city',
    in_hours: 6,
  },
]

export const sampleVenues: Omit<Schemas['MeetupVenue'], 'id' | 'osm_url' | 'gis_url' | 'yandex_url'>[] = [
  { name: 'Кофейня на углу', kind: 'cafe', address: 'Ленина, 1', distance_m: 350, opening_hours: 'Mo-Su 08:00-22:00', open_now: true },
  { name: 'Паб «Янтарь»', kind: 'pub', address: 'Мира, 12', distance_m: 900, opening_hours: null, open_now: null },
]
