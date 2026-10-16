// MSW handlers implementing contracts/openapi.yaml on top of the in-memory MockDb.
import { delay, http, HttpResponse, type DefaultBodyType, type HttpResponseResolver, type PathParams } from 'msw'
import type { Schemas } from '../api/client'
import { CONSENT_VERSION, cities, goals } from './data'
import { db, MAX_TAKEN, uuid } from './db'

const API = '*/api/v1'
const TOKEN = 'mock-access-token'

function problem(status: number, title: string, type = 'about:blank', detail?: string) {
  const body: Schemas['Problem'] = { type, title, status, ...(detail ? { detail } : {}) }
  return HttpResponse.json(body, { status, headers: { 'Content-Type': 'application/problem+json' } })
}

/** Wraps a resolver with the bearer check every protected endpoint has. */
function authed<P extends PathParams, B extends DefaultBodyType, R extends DefaultBodyType>(
  resolver: HttpResponseResolver<P, B, R>,
): HttpResponseResolver<P, B, R> {
  return async (info) => {
    if (info.request.headers.get('Authorization') !== `Bearer ${TOKEN}`) {
      return problem(401, 'Нужно войти заново', 'https://ayda.app/errors/unauthorized') as never
    }
    if (import.meta.env.MODE !== 'test') await delay(150)
    return resolver(info)
  }
}

export const handlers = [
  http.get(`${API}/health`, () => HttpResponse.json({ status: 'ok' as const })),

  http.post<never, { init_data: string }, DefaultBodyType>(`${API}/auth/telegram`, async ({ request }) => {
    const body = await request.json()
    if (!body?.init_data) return problem(422, 'Нет initData')
    if (body.init_data === 'invalid') return problem(401, 'Подпись Telegram не прошла проверку')
    const session: Schemas['Session'] = {
      access_token: TOKEN,
      expires_at: new Date(Date.now() + 86_400_000).toISOString(),
      user: db.me,
    }
    return HttpResponse.json(session)
  }),

  // ---- profile ----
  http.get(`${API}/me`, authed(() => HttpResponse.json(db.me))),
  http.delete(
    `${API}/me`,
    authed(() => {
      db.deletionRequested = true
      return new HttpResponse(null, { status: 202 })
    }),
  ),
  http.patch<never, Schemas['ProfileUpdate'], DefaultBodyType>(
    `${API}/me/profile`,
    authed(async ({ request }) => {
      const body = await request.json()
      if (body.city_id !== undefined) {
        const city = cities.find((c) => c.id === body.city_id)
        if (!city) return problem(422, 'Нет такого города')
        db.me.city = city
        db.me.timezone = city.timezone
      }
      if (body.theme) db.me.theme = body.theme
      if (body.reminders) db.me.reminders = body.reminders
      return HttpResponse.json(db.me)
    }),
  ),
  http.post(
    `${API}/me/onboarding/complete`,
    authed(() => {
      if (db.me.consent_required || !db.me.city) return problem(409, 'Сначала согласие и город')
      db.me.onboarded = true
      return HttpResponse.json(db.me)
    }),
  ),
  http.post<never, { version: string }, DefaultBodyType>(
    `${API}/me/consents`,
    authed(async ({ request }) => {
      const { version } = await request.json()
      if (version !== CONSENT_VERSION) return problem(422, 'Устаревшая версия согласия')
      db.me.consent_required = null
      return new HttpResponse(null, { status: 204 })
    }),
  ),
  http.get(`${API}/me/goals`, authed(() => HttpResponse.json({ goal_codes: db.goalCodes }))),
  http.put<never, Schemas['GoalSelection'], DefaultBodyType>(
    `${API}/me/goals`,
    authed(async ({ request }) => {
      const { goal_codes } = await request.json()
      if (goal_codes.length > 5 || goal_codes.some((c) => !goals.some((g) => g.code === c))) return problem(422, 'Неверные цели')
      db.goalCodes = goal_codes
      return HttpResponse.json({ goal_codes })
    }),
  ),
  http.get(`${API}/me/habits`, authed(() => HttpResponse.json({ items: db.habits }))),
  http.post<never, Schemas['HabitCreate'], DefaultBodyType>(
    `${API}/me/habits`,
    authed(async ({ request }) => {
      const body = await request.json()
      const text = body.text.trim()
      if (!text || text.length > 100) return problem(422, 'Привычка: от 1 до 100 символов')
      const habit: Schemas['Habit'] = { id: uuid(), direction: body.direction, text }
      db.habits.push(habit)
      return HttpResponse.json(habit, { status: 201 })
    }),
  ),
  http.delete<{ habit_id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/me/habits/:habit_id`,
    authed(({ params }) => {
      const before = db.habits.length
      db.habits = db.habits.filter((h) => h.id !== params.habit_id)
      return db.habits.length === before ? problem(404, 'Нет такой привычки') : new HttpResponse(null, { status: 204 })
    }),
  ),

  // ---- reference ----
  http.get(
    `${API}/cities`,
    authed(({ request }) => {
      const url = new URL(request.url)
      const query = url.searchParams.get('query')?.toLowerCase()
      const limit = Number(url.searchParams.get('limit') ?? 10)
      let items = cities
      if (query) items = cities.filter((c) => c.name.toLowerCase().includes(query))
      else if (url.searchParams.has('lat')) items = cities.filter((c) => c.region_name === 'Калининградская область')
      return HttpResponse.json({ items: items.slice(0, limit) })
    }),
  ),
  http.get(`${API}/goals`, authed(() => HttpResponse.json({ items: goals }))),

  // ---- day ----
  http.get(`${API}/days/today`, authed(() => HttpResponse.json(db.day()))),
  http.put<never, Schemas['CheckinInput'], DefaultBodyType>(
    `${API}/days/today/checkin`,
    authed(async ({ request }) => {
      const body = await request.json()
      if ((body.text ?? '').length > 1000) return problem(422, 'Не больше 1000 символов')
      db.submitCheckin(body)
      return HttpResponse.json(db.day(), { status: 202 })
    }),
  ),
  http.post<never, Schemas['OwnQuestInput'], DefaultBodyType>(
    `${API}/day-quests`,
    authed(async ({ request }) => {
      const body = await request.json()
      if (db.takenCount() >= MAX_TAKEN) return problem(409, 'Уже взято 3 квеста', 'https://ayda.app/errors/daily-limit-reached')
      if (!body.title.trim()) return problem(422, 'Нужно название')
      return HttpResponse.json(db.addOwn(body), { status: 201 })
    }),
  ),
  http.post<{ quest_id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/day-quests/:quest_id/take`,
    authed(({ params }) => {
      const q = db.quest(params.quest_id)
      if (!q) return problem(404, 'Квест не найден')
      if (q.state !== 'offered') return problem(409, 'Квест уже не предлагается')
      if (db.takenCount() >= MAX_TAKEN) return problem(409, 'Уже взято 3 квеста', 'https://ayda.app/errors/daily-limit-reached')
      return HttpResponse.json(db.take(q))
    }),
  ),
  http.post<{ quest_id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/day-quests/:quest_id/replace`,
    authed(({ params }) => {
      const q = db.quest(params.quest_id)
      if (!q) return problem(404, 'Квест не найден')
      if (q.state !== 'offered') return problem(409, 'Квест уже не предлагается')
      if (db.replacementsLeft <= 0) return problem(409, 'Замены на сегодня закончились', 'https://ayda.app/errors/no-replacements-left')
      const replacement = db.replace(q)
      return HttpResponse.json({ replaced: { ...q }, replacement, replacements_left: db.replacementsLeft })
    }),
  ),
  http.post<{ quest_id: string }, Schemas['CompleteQuestInput'], DefaultBodyType>(
    `${API}/day-quests/:quest_id/complete`,
    authed(async ({ params, request }) => {
      const q = db.quest(params.quest_id)
      if (!q) return problem(404, 'Квест не найден')
      if (q.state !== 'taken') return problem(409, 'Квест не взят или уже выполнен')
      const body = await request.json()
      const media = body.media_ids ?? []
      if (body.visibility === 'friends' && (media.length < 1 || media.length > 3)) return problem(422, 'Для друзей нужно 1-3 фото')
      if (body.visibility !== 'friends' && media.length > 0) return problem(422, 'Фото только для друзей')
      return HttpResponse.json(db.complete(q, body))
    }),
  ),

  // ---- media ----
  http.post<never, { content_type: string; size_bytes: number }, DefaultBodyType>(
    `${API}/media/uploads`,
    authed(async ({ request }) => {
      const body = await request.json()
      if (body.size_bytes > 10_485_760) return problem(422, 'Фото больше 10 МБ')
      const id = uuid()
      db.uploads.set(id, { url: null })
      const slot: Schemas['UploadSlot'] = {
        media_id: id,
        upload_url: new URL(`/mock-s3/${id}`, request.url).href,
        headers: { 'Content-Type': body.content_type },
        expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
      }
      return HttpResponse.json(slot, { status: 201 })
    }),
  ),
  http.put<{ media_id: string }, DefaultBodyType, DefaultBodyType>('*/mock-s3/:media_id', async ({ params, request }) => {
    const upload = db.uploads.get(params.media_id)
    if (!upload) return new HttpResponse(null, { status: 403 })
    const blob = await request.blob()
    upload.url = typeof URL.createObjectURL === 'function' ? URL.createObjectURL(blob) : null
    return new HttpResponse(null, { status: 200 })
  }),

  // ---- social ----
  http.get(
    `${API}/feed`,
    authed(({ request }) => {
      const url = new URL(request.url)
      return HttpResponse.json(db.feed(url.searchParams.get('cursor'), Number(url.searchParams.get('limit') ?? 20)))
    }),
  ),
  http.delete<{ post_id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/posts/:post_id`,
    authed(({ params }) => {
      const post = db.post(params.post_id)
      if (!post) return problem(404, 'Пост не найден')
      if (post.authorId !== db.me.id) return problem(403, 'Можно удалить только свой пост')
      db.posts = db.posts.filter((p) => p !== post)
      return new HttpResponse(null, { status: 204 })
    }),
  ),
  http.put<{ post_id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/posts/:post_id/like`,
    authed(({ params }) => {
      const post = db.post(params.post_id)
      if (!post) return problem(404, 'Пост не найден')
      if (!post.liked_by_me) {
        post.liked_by_me = true
        post.like_count += 1
      }
      return HttpResponse.json({ like_count: post.like_count, liked_by_me: true })
    }),
  ),
  http.delete<{ post_id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/posts/:post_id/like`,
    authed(({ params }) => {
      const post = db.post(params.post_id)
      if (!post) return problem(404, 'Пост не найден')
      if (post.liked_by_me) {
        post.liked_by_me = false
        post.like_count -= 1
      }
      return HttpResponse.json({ like_count: post.like_count, liked_by_me: false })
    }),
  ),
  http.get<{ post_id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/posts/:post_id/comments`,
    authed(({ params }) => {
      const post = db.post(params.post_id)
      if (!post) return problem(404, 'Пост не найден')
      return HttpResponse.json({ items: db.commentsOf(post), next_cursor: null })
    }),
  ),
  http.post<{ post_id: string }, { text: string }, DefaultBodyType>(
    `${API}/posts/:post_id/comments`,
    authed(async ({ params, request }) => {
      const post = db.post(params.post_id)
      if (!post) return problem(404, 'Пост не найден')
      const text = (await request.json()).text.trim()
      if (!text || text.length > 500) return problem(422, 'Комментарий: от 1 до 500 символов')
      return HttpResponse.json(db.addComment(post, text), { status: 201 })
    }),
  ),
  http.delete<{ comment_id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/comments/:comment_id`,
    authed(({ params }) => {
      for (const post of db.posts) {
        const c = db.commentsOf(post).find((x) => x.id === params.comment_id)
        if (!c) continue
        if (!c.can_delete) return problem(403, 'Нельзя удалить чужой комментарий')
        post.comments = post.comments.filter((x) => x.id !== c.id)
        post.comment_count = post.comments.length
        return new HttpResponse(null, { status: 204 })
      }
      return problem(404, 'Комментарий не найден')
    }),
  ),
  http.post(`${API}/invites`, authed(() => HttpResponse.json(db.createInvite(), { status: 201 }))),
  http.post<{ code: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/invites/:code/accept`,
    authed(({ params }) => {
      const result = db.acceptInvite(params.code)
      if (result === 'not_found') return problem(404, 'Приглашение не найдено')
      if (result === 'own') return problem(409, 'Это твоё приглашение')
      if (result === 'expired') return problem(410, 'Приглашение истекло')
      return HttpResponse.json(result)
    }),
  ),
  http.get(
    `${API}/friends`,
    authed(() =>
      HttpResponse.json({
        items: [...db.friends]
          .sort((a, b) => a.first_name.localeCompare(b.first_name, 'ru'))
          .map(({ id, first_name, avatar_url, since }) => ({ id, first_name, avatar_url, since })),
      }),
    ),
  ),
  http.delete<{ user_id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/friends/:user_id`,
    authed(({ params }) => {
      const before = db.friends.length
      db.friends = db.friends.filter((f) => f.id !== params.user_id)
      if (db.friends.length === before) return problem(404, 'Нет такого друга')
      db.posts = db.posts.filter((p) => p.authorId !== params.user_id)
      return new HttpResponse(null, { status: 204 })
    }),
  ),
  http.get(
    `${API}/ladder`,
    authed(({ request }) => {
      const week = new URL(request.url).searchParams.get('week') === 'previous' ? 'previous' : 'current'
      return HttpResponse.json(db.ladder(week))
    }),
  ),

  // ---- chats (US-17); realtime is not mocked, so the app polls ----
  http.post(`${API}/realtime/token`, authed(() => problem(503, 'Чат временно недоступен', 'https://ayda.app/errors/realtime-unavailable'))),
  http.get(`${API}/conversations`, authed(() => HttpResponse.json({ items: db.listConversations() }))),
  http.post<never, { user_id: string }, DefaultBodyType>(
    `${API}/conversations/direct`,
    authed(async ({ request }) => {
      const { user_id } = await request.json()
      const result = db.openDirect(user_id)
      if (result === 'not_friends') return problem(403, 'Писать можно только друзьям', 'https://ayda.app/errors/not-friends')
      return HttpResponse.json(result)
    }),
  ),
  http.get<{ id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/conversations/:id`,
    authed(({ params }) => {
      const c = db.findConversation(params.id)
      return c ? HttpResponse.json(db.conversation(c)) : problem(404, 'Чат не найден')
    }),
  ),
  http.get<{ id: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/conversations/:id/messages`,
    authed(({ params, request }) => {
      const c = db.findConversation(params.id)
      if (!c) return problem(404, 'Чат не найден')
      const url = new URL(request.url)
      return HttpResponse.json(db.messages(c, url.searchParams.get('cursor'), Number(url.searchParams.get('limit') ?? 20)))
    }),
  ),
  http.post<{ id: string }, Schemas['MessageInput'], DefaultBodyType>(
    `${API}/conversations/:id/messages`,
    authed(async ({ params, request }) => {
      const c = db.findConversation(params.id)
      if (!c) return problem(404, 'Чат не найден')
      const body = await request.json()
      if (!body.text?.trim() || body.text.length > 2000) return problem(422, 'Пустое или слишком длинное сообщение')
      const result = db.sendMessage(c, body)
      if (result === 'closed') return problem(403, 'Этот чат закрыт для новых сообщений', 'https://ayda.app/errors/chat-closed')
      if (result.created && import.meta.env.MODE !== 'test') setTimeout(() => db.replyFrom(c, '👍'), 2500)
      return HttpResponse.json(result.message, { status: result.created ? 201 : 200 })
    }),
  ),
  http.delete<{ id: string; messageId: string }, DefaultBodyType, DefaultBodyType>(
    `${API}/conversations/:id/messages/:messageId`,
    authed(({ params }) => {
      const c = db.findConversation(params.id)
      const m = c?.messages.find((x) => x.id === Number(params.messageId))
      if (!c || !m) return problem(404, 'Сообщение не найдено')
      if (m.author.id !== db.me.id) return problem(403, 'Удалить можно только своё сообщение')
      c.messages = c.messages.filter((x) => x !== m)
      return new HttpResponse(null, { status: 204 })
    }),
  ),
  http.post<{ id: string }, { last_read_message_id: number }, DefaultBodyType>(
    `${API}/conversations/:id/read`,
    authed(async ({ params, request }) => {
      const c = db.findConversation(params.id)
      if (!c) return problem(404, 'Чат не найден')
      const { last_read_message_id } = await request.json()
      const newest = c.messages.at(-1)?.id ?? 0
      c.lastRead = Math.max(c.lastRead ?? 0, Math.min(last_read_message_id, newest))
      return new HttpResponse(null, { status: 204 })
    }),
  ),
]
