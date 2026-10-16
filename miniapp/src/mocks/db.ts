// In-memory backend used by the mock API in development and tests.
// It follows the contract and the PRD rules closely enough to drive every screen.
import type { Schemas } from '../api/client'
import { catalog, CONSENT_VERSION, friendNames, sampleCaptions, type CatalogQuest } from './data'

type DayQuest = Schemas['DayQuest']
type Post = Schemas['Post']
type Comment = Schemas['Comment']
type Friend = Schemas['Friend']
type Visibility = Schemas['Visibility']

export const MAX_TAKEN = 3
export const MAX_REPLACEMENTS = 5

export function uuid(): string {
  return globalThis.crypto?.randomUUID?.() ?? `00000000-0000-4000-8000-${Math.random().toString(16).slice(2, 14).padEnd(12, '0')}`
}

export function basePoints(durationMin: number): number {
  if (durationMin <= 15) return 10
  if (durationMin <= 30) return 20
  if (durationMin <= 60) return 35
  return 50
}

export const VISIBILITY_MULTIPLIER: Record<Visibility, number> = { friends: 1, routine: 0.75, personal: 0.5 }

export function streakMultiplier(days: number): number {
  return 1 + Math.min(3, Math.floor(days / 7)) * 0.1
}

function localDate(d = new Date()): string {
  return d.toISOString().slice(0, 10)
}

function tomorrowAt4(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  d.setHours(4, 0, 0, 0)
  return d.toISOString()
}

function minutesAgo(min: number): string {
  return new Date(Date.now() - min * 60_000).toISOString()
}

/** A small abstract picture as a data URI, standing in for a proof photo. */
function placeholderPhoto(seed: number): Schemas['Photo'] {
  const hues = ['#FF5FA2', '#FF9E7A', '#7AC7FF', '#9BE07A', '#C9A2FF']
  const accent = hues[seed % hues.length]
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="440" viewBox="0 0 600 440"><rect width="600" height="440" fill="#222326"/><circle cx="120" cy="300" r="190" fill="none" stroke="#34363B" stroke-width="44"/><circle cx="520" cy="40" r="140" fill="${accent}" opacity="0.85"/></svg>`
  return { id: uuid(), url: `data:image/svg+xml,${encodeURIComponent(svg)}`, width: 600, height: 440 }
}

interface StoredQuest extends DayQuest {
  catalogIndex: number | null
}

interface StoredPost extends Post {
  authorId: string
  comments: Comment[]
}

interface StoredConversation {
  id: string
  peerId: string
  createdAt: string
  messages: Schemas['Message'][]
  lastRead: number | null
}

export interface MockOptions {
  /** Skip consent and onboarding: a returning user. */
  onboarded?: boolean
  /** How long the pool stays in `generating`. */
  poolDelayMs?: number
  /** Seed friends with posts and ladder points. */
  withFriends?: boolean
}

export class MockDb {
  me!: Schemas['Me']
  goalCodes: string[] = []
  habits: Schemas['Habit'][] = []
  checkin: Schemas['Checkin'] | null = null
  poolStatus: Schemas['PoolStatus'] = 'none'
  poolReadyAt = 0
  quests: StoredQuest[] = []
  replacementsLeft = MAX_REPLACEMENTS
  pointsToday = 0
  pointsWeek = 0
  streak: Schemas['Streak'] = { current_days: 0, best_days: 0, freeze_available: true }
  uploads = new Map<string, { url: string | null }>()
  posts: StoredPost[] = []
  friends: (Friend & { points: number; streak_days: number })[] = []
  invites = new Map<string, { inviterId: string | null; expiresAt: string }>()
  conversations: StoredConversation[] = []
  private nextMessageId = 1
  poolDelayMs = 1200
  deletionRequested = false

  constructor(options: MockOptions = {}) {
    this.reset(options)
  }

  reset({ onboarded = false, poolDelayMs = 1200, withFriends = true }: MockOptions = {}): void {
    this.poolDelayMs = poolDelayMs
    this.me = {
      id: uuid(),
      first_name: 'Саша',
      last_name: null,
      username: 'sasha',
      avatar_url: null,
      city: onboarded ? { id: 3, name: 'Калининград', region_name: 'Калининградская область', timezone: 'Europe/Kaliningrad' } : null,
      timezone: onboarded ? 'Europe/Kaliningrad' : 'Europe/Moscow',
      theme: 'graphite',
      reminders: { morning_at: '08:30', evening_at: '20:30' },
      consent_required: onboarded ? null : CONSENT_VERSION,
      onboarded,
    }
    this.goalCodes = onboarded ? ['more_movement', 'own_project'] : []
    this.habits = []
    this.checkin = null
    this.poolStatus = 'none'
    this.quests = []
    this.replacementsLeft = MAX_REPLACEMENTS
    this.pointsToday = 0
    this.pointsWeek = onboarded ? 185 : 0
    this.streak = onboarded ? { current_days: 12, best_days: 15, freeze_available: true } : { current_days: 0, best_days: 0, freeze_available: true }
    this.uploads.clear()
    this.posts = []
    this.friends = []
    this.invites.clear()
    this.conversations = []
    this.nextMessageId = 1
    this.deletionRequested = false
    // A known invite from a friend who is not yet a friend, for invite acceptance in dev
    this.invites.set('welcome-invite-code', { inviterId: null, expiresAt: new Date(Date.now() + 7 * 86_400_000).toISOString() })
    if (withFriends) this.seedFriends()
  }

  private seedFriends(): void {
    const points = [410, 265, 190, 105, 80]
    const streaks = [21, 9, 4, 12, 0]
    this.friends = friendNames.map((name, i) => ({
      id: uuid(),
      first_name: name,
      avatar_url: null,
      since: minutesAgo(60 * 24 * (30 + i)),
      points: points[i] ?? 0,
      streak_days: streaks[i] ?? 0,
    }))
    const titles: [string, Schemas['Category']][] = [
      ['Пробежка 5 км', 'sport'],
      ['Музей янтаря', 'city'],
      ['Час на свой проект', 'project'],
    ]
    this.friends.slice(0, 4).forEach((friend, i) => {
      const routine = i === 1
      const [title, category] = titles[i % titles.length]!
      this.posts.push({
        id: uuid(),
        authorId: friend.id,
        author: { id: friend.id, first_name: friend.first_name, avatar_url: null },
        kind: routine ? 'routine' : 'proof',
        quest_title: routine ? null : title,
        category: routine ? 'rest' : category,
        caption: routine ? null : (sampleCaptions[i % sampleCaptions.length] ?? null),
        photos: routine ? [] : [placeholderPhoto(i)],
        local_date: localDate(),
        created_at: minutesAgo(20 + i * 70),
        like_count: [14, 3, 6, 1][i] ?? 0,
        liked_by_me: false,
        comment_count: 0,
        comments: [],
      })
    })
    const first = this.posts[0]
    if (first) {
      const friend = this.friends[1]!
      first.comments.push({
        id: uuid(),
        author: { id: friend.id, first_name: friend.first_name, avatar_url: null },
        text: 'Огонь! Завтра со мной?',
        created_at: minutesAgo(10),
        can_delete: false,
      })
      first.comment_count = 1
    }
    const lena = this.friends[0]!
    const chat = this.openDirect(lena.id)
    if (chat !== 'not_friends') {
      const stored = this.conversations[0]!
      this.addMessage(stored, lena.id, 'Привет! Завтра бегаем?', minutesAgo(40))
      this.addMessage(stored, this.me.id, 'Давай, в 8 у парка', minutesAgo(35))
      stored.lastRead = this.nextMessageId - 1
      this.addMessage(stored, lena.id, 'Договорились 🙌', minutesAgo(5))
    }
  }

  // ---- chats (US-17) ----

  private summary(id: string): Schemas['UserSummary'] {
    if (id === this.me.id) return { id, first_name: this.me.first_name, avatar_url: this.me.avatar_url ?? null }
    const f = this.friends.find((x) => x.id === id)
    return { id, first_name: f?.first_name ?? 'Удалённый пользователь', avatar_url: f?.avatar_url ?? null }
  }

  private addMessage(c: StoredConversation, authorId: string, text: string, at = new Date().toISOString(), clientId: string | null = null): Schemas['Message'] {
    const message = { id: this.nextMessageId++, conversation_id: c.id, author: this.summary(authorId), text, created_at: at, client_id: clientId }
    c.messages.push(message)
    if (authorId === this.me.id) c.lastRead = message.id
    return message
  }

  conversation(c: StoredConversation): Schemas['Conversation'] {
    const peer = this.summary(c.peerId)
    const last = c.messages.at(-1) ?? null
    return {
      id: c.id,
      kind: 'dm',
      title: peer.first_name,
      peer,
      coop_id: null,
      members: [peer],
      can_send: this.friends.some((f) => f.id === c.peerId),
      last_message: last,
      unread_count: c.messages.filter((m) => m.id > (c.lastRead ?? 0) && m.author.id !== this.me.id).length,
      last_read_message_id: c.lastRead,
      updated_at: last?.created_at ?? c.createdAt,
    }
  }

  listConversations(): Schemas['Conversation'][] {
    return this.conversations.map((c) => this.conversation(c)).sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  }

  findConversation(id: string): StoredConversation | undefined {
    return this.conversations.find((c) => c.id === id)
  }

  openDirect(userId: string): Schemas['Conversation'] | 'not_friends' {
    if (!this.friends.some((f) => f.id === userId)) return 'not_friends'
    let c = this.conversations.find((x) => x.peerId === userId)
    if (!c) {
      c = { id: uuid(), peerId: userId, createdAt: new Date().toISOString(), messages: [], lastRead: null }
      this.conversations.push(c)
    }
    return this.conversation(c)
  }

  messages(c: StoredConversation, cursor: string | null, limit: number): Schemas['MessagePage'] {
    const before = cursor ? Number(cursor) : Infinity
    const older = c.messages.filter((m) => m.id < before).reverse()
    const items = older.slice(0, limit)
    return { items, next_cursor: older.length > limit ? String(items.at(-1)!.id) : null }
  }

  sendMessage(c: StoredConversation, input: Schemas['MessageInput']): { message: Schemas['Message']; created: boolean } | 'closed' {
    const existing = c.messages.find((m) => m.client_id === input.client_id)
    if (existing) return { message: existing, created: false }
    if (!this.friends.some((f) => f.id === c.peerId)) return 'closed'
    return { message: this.addMessage(c, this.me.id, input.text.trim(), undefined, input.client_id), created: true }
  }

  /** Dev only: the friend answers, as if over realtime (picked up by polling). */
  replyFrom(c: StoredConversation, text: string): void {
    this.addMessage(c, c.peerId, text)
  }

  // ---- day ----

  day(): Schemas['Day'] {
    if (this.poolStatus === 'generating' && Date.now() >= this.poolReadyAt) this.buildPool()
    return {
      local_date: localDate(),
      checkin: this.checkin,
      pool_status: this.poolStatus,
      weather: { temperature_c: 9, condition: 'clear' },
      quests: this.quests.filter((q) => q.state !== 'replaced').map(publicQuest),
      limits: { taken: this.takenCount(), max_taken: MAX_TAKEN, replacements_left: this.replacementsLeft },
      points_today: this.pointsToday,
      points_week: this.pointsWeek,
      streak: this.streak,
    }
  }

  takenCount(): number {
    return this.quests.filter((q) => q.state === 'taken' || q.state === 'completed').length
  }

  submitCheckin(input: Schemas['CheckinInput']): void {
    this.checkin = { text: input.text ?? '', mood: input.mood, submitted_at: new Date().toISOString() }
    // Quests not taken yet are rebuilt; taken and completed stay
    this.quests = this.quests.filter((q) => q.state === 'taken' || q.state === 'completed')
    this.poolStatus = 'generating'
    this.poolReadyAt = Date.now() + this.poolDelayMs
    if (this.poolDelayMs <= 0) this.buildPool()
  }

  private usedCatalog(): Set<number> {
    return new Set(this.quests.map((q) => q.catalogIndex).filter((i): i is number => i !== null))
  }

  private buildPool(): void {
    const checkin = this.checkin
    const tasks = (checkin?.text ?? '')
      .split(/\n|,/)
      .map((s) => s.trim())
      .filter((s) => s.length > 2)
      .slice(0, 2)
    const fresh: StoredQuest[] = tasks.map((title) => ({
      ...newQuest({ title: capitalize(title), category: 'project', duration_min: 60, outdoor: false, why: 'Из твоего плана на день' }),
      source: 'checkin_task',
      catalogIndex: null,
    }))
    const used = this.usedCatalog()
    const wanted = 6 - this.quests.length - fresh.length
    const order = catalog.map((_, i) => i).filter((i) => !used.has(i))
    if (checkin?.mood === 'tired') {
      const rest = order.findIndex((i) => catalog[i]!.category === 'rest')
      if (rest > 0) order.unshift(...order.splice(rest, 1))
    }
    for (const i of order.slice(0, Math.max(0, wanted))) fresh.push({ ...newQuest(catalog[i]!), catalogIndex: i })
    this.quests.push(...fresh)
    this.poolStatus = 'ready'
  }

  quest(id: string): StoredQuest | undefined {
    return this.quests.find((q) => q.id === id)
  }

  take(q: StoredQuest): DayQuest {
    q.state = 'taken'
    return publicQuest(q)
  }

  replace(q: StoredQuest): Schemas['DayQuest'] | null {
    q.state = 'replaced'
    this.replacementsLeft -= 1
    const used = this.usedCatalog()
    const original = q.catalogIndex !== null ? catalog[q.catalogIndex] : undefined
    const candidates = catalog
      .map((c, i) => ({ c, i }))
      .filter(({ i }) => !used.has(i))
      .sort((a, b) => Number(a.c.category === original?.category) - Number(b.c.category === original?.category))
    const next = candidates[0]
    if (!next) return null
    const replacement: StoredQuest = { ...newQuest(next.c), catalogIndex: next.i }
    // Keep pool order: the replacement takes the replaced quest's place
    this.quests.splice(this.quests.indexOf(q) + 1, 0, replacement)
    return publicQuest(replacement)
  }

  addOwn(input: Schemas['OwnQuestInput']): DayQuest {
    const q: StoredQuest = {
      ...newQuest({ title: input.title, category: input.category, duration_min: input.duration_min, outdoor: false, why: null }),
      source: 'custom',
      state: 'taken',
      catalogIndex: null,
    }
    this.quests.push(q)
    return publicQuest(q)
  }

  complete(q: StoredQuest, input: Schemas['CompleteQuestInput']): Schemas['Completion'] {
    const firstToday = this.quests.every((x) => x.state !== 'completed')
    if (firstToday) {
      this.streak = {
        ...this.streak,
        current_days: this.streak.current_days + 1,
        best_days: Math.max(this.streak.best_days, this.streak.current_days + 1),
      }
    }
    const vm = VISIBILITY_MULTIPLIER[input.visibility]
    const sm = streakMultiplier(this.streak.current_days)
    const points = Math.round(q.base_points * vm * sm)
    q.state = 'completed'
    q.visibility = input.visibility
    q.points_awarded = points
    this.pointsToday += points
    this.pointsWeek += points
    let postId: string | null = null
    if (input.visibility !== 'personal') {
      const proof = input.visibility === 'friends'
      const post: StoredPost = {
        id: uuid(),
        authorId: this.me.id,
        author: { id: this.me.id, first_name: this.me.first_name, avatar_url: this.me.avatar_url ?? null },
        kind: proof ? 'proof' : 'routine',
        quest_title: proof ? q.title : null,
        category: q.category,
        caption: proof ? input.caption?.trim() || null : null,
        photos: proof
          ? (input.media_ids ?? []).map((id, i) => {
              const upload = this.uploads.get(id)
              return upload?.url ? { id, url: upload.url, width: 600, height: 440 } : { ...placeholderPhoto(i), id }
            })
          : [],
        local_date: localDate(),
        created_at: new Date().toISOString(),
        like_count: 0,
        liked_by_me: false,
        comment_count: 0,
        comments: [],
      }
      this.posts.unshift(post)
      postId = post.id
    }
    return {
      quest: publicQuest(q),
      points_awarded: points,
      points_breakdown: { base: q.base_points, visibility_multiplier: vm, streak_multiplier: sm },
      streak: this.streak,
      post_id: postId,
    }
  }

  // ---- social ----

  feed(cursor: string | null, limit: number): Schemas['PostPage'] {
    const start = cursor ? Number(cursor) : 0
    const page = this.posts.slice(start, start + limit)
    const next = start + limit < this.posts.length ? String(start + limit) : null
    return { items: page.map((p) => this.publicPost(p)), next_cursor: next }
  }

  publicPost(p: StoredPost): Post {
    const { authorId, comments, ...post } = p
    return post
  }

  post(id: string): StoredPost | undefined {
    return this.posts.find((p) => p.id === id)
  }

  addComment(p: StoredPost, text: string): Comment {
    const c: Comment = {
      id: uuid(),
      author: { id: this.me.id, first_name: this.me.first_name, avatar_url: this.me.avatar_url ?? null },
      text,
      created_at: new Date().toISOString(),
      can_delete: true,
    }
    p.comments.push(c)
    p.comment_count = p.comments.length
    return c
  }

  commentsOf(p: StoredPost): Comment[] {
    const mine = p.authorId === this.me.id
    return p.comments.map((c) => ({ ...c, can_delete: mine || c.author.id === this.me.id }))
  }

  createInvite(): Schemas['Invite'] {
    const code = Math.random().toString(36).slice(2, 12).padEnd(10, 'x')
    const expiresAt = new Date(Date.now() + 7 * 86_400_000).toISOString()
    this.invites.set(code, { inviterId: this.me.id, expiresAt })
    return { code, url: `https://t.me/ayda_quest_bot?startapp=${code}`, expires_at: expiresAt }
  }

  acceptInvite(code: string): Friend | 'not_found' | 'own' | 'expired' {
    const invite = this.invites.get(code)
    if (!invite) return 'not_found'
    if (invite.inviterId === this.me.id) return 'own'
    if (Date.parse(invite.expiresAt) < Date.now()) return 'expired'
    const existing = this.friends.find((f) => f.id === invite.inviterId)
    if (existing) return publicFriend(existing)
    const friend = { id: invite.inviterId ?? uuid(), first_name: 'Оля', avatar_url: null, since: new Date().toISOString(), points: 0, streak_days: 0 }
    invite.inviterId = friend.id
    this.friends.push(friend)
    return publicFriend(friend)
  }

  ladder(week: 'current' | 'previous'): Schemas['Ladder'] {
    const rows = [
      { user: { id: this.me.id, first_name: this.me.first_name, avatar_url: this.me.avatar_url ?? null }, points: week === 'current' ? this.pointsWeek : 260, streak_days: this.streak.current_days, is_me: true },
      ...this.friends.map((f, i) => ({
        user: { id: f.id, first_name: f.first_name, avatar_url: f.avatar_url ?? null },
        points: week === 'current' ? f.points : [330, 290, 120, 240, 60][i % 5]!,
        streak_days: f.streak_days,
        is_me: false,
      })),
    ].sort((a, b) => b.points - a.points || b.streak_days - a.streak_days)
    const monday = new Date()
    monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7) - (week === 'previous' ? 7 : 0))
    return { week_start: localDate(monday), entries: rows.map((r, i) => ({ rank: i + 1, ...r })) }
  }
}

function newQuest(c: Omit<CatalogQuest, 'why'> & { why: string | null }): DayQuest {
  return {
    id: uuid(),
    source: 'catalog',
    title: c.title,
    description: c.description ?? null,
    category: c.category,
    duration_min: c.duration_min,
    base_points: basePoints(c.duration_min),
    why: c.why,
    outdoor: c.outdoor,
    state: 'offered',
    visibility: null,
    points_awarded: null,
    expires_at: tomorrowAt4(),
  }
}

function publicQuest(q: StoredQuest | DayQuest): DayQuest {
  const { catalogIndex, ...rest } = q as StoredQuest
  return { ...rest }
}

function publicFriend(f: Friend & { points?: number; streak_days?: number }): Friend {
  return { id: f.id, first_name: f.first_name, avatar_url: f.avatar_url ?? null, since: f.since }
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export const db = new MockDb()
