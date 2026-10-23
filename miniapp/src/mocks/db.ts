// In-memory backend used by the mock API in development and tests.
// It follows the contract and the PRD rules closely enough to drive every screen.
import type { Schemas } from '../api/client'
import { catalog, CONSENT_VERSION, friendNames, sampleCaptions, sampleEvents, sampleVenues, type CatalogQuest } from './data'

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
  /** DM: the friend. Co-op chat: the co-op owner (who answers in dev). */
  peerId: string
  coopId: string | null
  createdAt: string
  messages: Schemas['Message'][]
  lastRead: number | null
}

interface StoredCoop {
  id: string
  title: string
  category: Schemas['Category']
  duration_min: number
  ownerId: string
  expiresAt: string
  participants: { userId: string; status: Schemas['CoopStatus']; questId: string | null; completed: boolean }[]
  conversationId: string
  parts?: StoredPart[]
  place?: Schemas['Place']
  startsAt?: string
}

interface StoredPart {
  id: string
  title: string
  category: Schemas['Category']
  duration_min: number
  place: Schemas['Place'] | null
  assigneeId: string
  opensAfter: string | null
  state: 'locked' | 'open' | 'done'
  items: Schemas['CoopItem'][]
  questId: string | null
  handoffToId: string | null
}

export interface PlanPartSpec {
  title: string
  assigneeId: string
  items?: string[]
  place?: Schemas['Place']
  /** Index of an earlier part. */
  opensAfter?: number
}

export const COOP_BONUS_SHARE = 0.5

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
  coops: StoredCoop[] = []
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
    this.coops = []
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
    // An invitation from a friend who has already done the quest: joining and completing it
    // brings the co-op bonus in dev
    const dima = this.friends[1]!
    const conversation: StoredConversation = { id: uuid(), peerId: dima.id, coopId: null, createdAt: minutesAgo(30), messages: [], lastRead: null }
    const coop: StoredCoop = {
      id: uuid(),
      title: 'Прогулка на 10 000 шагов',
      category: 'walk',
      duration_min: 60,
      ownerId: dima.id,
      expiresAt: tomorrowAt4(),
      participants: [
        { userId: dima.id, status: 'owner', questId: uuid(), completed: true },
        { userId: this.me.id, status: 'invited', questId: null, completed: false },
      ],
      conversationId: conversation.id,
    }
    conversation.coopId = coop.id
    this.coops.push(coop)
    this.conversations.push(conversation)
    this.addMessage(conversation, dima.id, 'Я уже прошёл, твоя очередь 🙂', minutesAgo(25))
  }

  // ---- co-op quests (US-18) ----

  publicCoop(c: StoredCoop): Schemas['Coop'] {
    const me = c.participants.find((p) => p.userId === this.me.id)!
    const joined = me.status === 'owner' || me.status === 'accepted'
    const people = c.participants.filter((p) => p.status === 'owner' || p.status === 'accepted')
    return {
      id: c.id,
      title: c.title,
      category: c.category,
      duration_min: c.duration_min,
      owner: this.summary(c.ownerId),
      my_status: me.status,
      participants: c.participants.map((p) => ({ user: this.summary(p.userId), status: p.status, completed: p.completed })),
      my_quest_id: joined ? me.questId : null,
      conversation_id: joined ? c.conversationId : null,
      expires_at: c.expiresAt,
      bonus_awarded: people.length >= 2 && people.every((p) => p.completed),
      kind: c.parts ? 'parts' : 'same',
      place: c.place ?? null,
      starts_at: c.startsAt ?? null,
      ...(c.parts ? { parts: c.parts.map((part, i) => this.publicPart(part, i)) } : {}),
    }
  }

  private publicPart(part: StoredPart, position: number): Schemas['CoopPart'] {
    return {
      id: part.id,
      position,
      title: part.title,
      category: part.category,
      duration_min: part.duration_min,
      place: part.place,
      starts_at: null,
      assignee: this.summary(part.assigneeId),
      state: part.state,
      opens_after: part.opensAfter,
      items: part.items,
      my_quest_id: part.assigneeId === this.me.id && part.state === 'open' ? part.questId : null,
      handoff: part.handoffToId ? { to: this.summary(part.handoffToId), for_me: part.handoffToId === this.me.id } : null,
    }
  }

  /** A plan of parts owned by the user, with the friends already in (the dev counterpart of createPlan). */
  addPlan(title: string, friendIds: string[], specs: PlanPartSpec[]): StoredCoop {
    const conversation: StoredConversation = { id: uuid(), peerId: friendIds[0]!, coopId: null, createdAt: new Date().toISOString(), messages: [], lastRead: null }
    const parts: StoredPart[] = []
    for (const spec of specs) {
      parts.push({
        id: uuid(),
        title: spec.title,
        category: 'home',
        duration_min: 30,
        place: spec.place ?? null,
        assigneeId: spec.assigneeId,
        opensAfter: spec.opensAfter === undefined ? null : parts[spec.opensAfter]!.id,
        state: 'locked',
        items: (spec.items ?? []).map((text) => ({ id: uuid(), text, done: false })),
        questId: null,
        handoffToId: null,
      })
    }
    const coop: StoredCoop = {
      id: uuid(),
      title,
      category: 'home',
      duration_min: 60,
      ownerId: this.me.id,
      expiresAt: tomorrowAt4(),
      participants: [
        { userId: this.me.id, status: 'owner', questId: null, completed: false },
        ...friendIds.map((userId) => ({ userId, status: 'accepted' as const, questId: null, completed: false })),
      ],
      conversationId: conversation.id,
      parts,
    }
    conversation.coopId = coop.id
    this.coops.push(coop)
    this.conversations.push(conversation)
    for (const part of parts) if (!part.opensAfter) this.openPart(coop, part)
    return coop
  }

  private openPart(coop: StoredCoop, part: StoredPart) {
    part.state = 'open'
    if (part.assigneeId !== this.me.id) return
    part.questId = uuid()
    this.quests.push({
      ...newQuest({ title: part.title, category: part.category, duration_min: part.duration_min, outdoor: false, why: null }),
      id: part.questId,
      source: 'coop',
      state: 'taken',
      coop_id: coop.id,
      catalogIndex: null,
    })
  }

  private partOf(c: StoredCoop, partId: string): StoredPart | undefined {
    return c.parts?.find((x) => x.id === partId)
  }

  setItem(c: StoredCoop, partId: string, itemId: string, done: boolean): Schemas['Coop'] | 'not_found' | 'forbidden' | 'locked' | 'done' {
    const part = this.partOf(c, partId)
    const item = part?.items.find((x) => x.id === itemId)
    if (!part || !item) return 'not_found'
    if (part.assigneeId !== this.me.id) return 'forbidden'
    if (part.state === 'locked') return 'locked'
    if (part.state === 'done') return 'done'
    item.done = done
    return this.publicCoop(c)
  }

  offerHandoff(c: StoredCoop, partId: string, friendId: string): Schemas['Coop'] | 'not_found' | 'forbidden' | 'pending' | 'self' | 'not_joined' | 'done' {
    const part = this.partOf(c, partId)
    if (!part) return 'not_found'
    if (part.assigneeId !== this.me.id) return 'forbidden'
    if (friendId === this.me.id) return 'self'
    if (part.state === 'done') return 'done'
    if (part.handoffToId) return 'pending'
    if (!c.participants.some((p) => p.userId === friendId && (p.status === 'owner' || p.status === 'accepted'))) return 'not_joined'
    part.handoffToId = friendId
    return this.publicCoop(c)
  }

  withdrawHandoff(c: StoredCoop, partId: string): Schemas['Coop'] | 'not_found' | 'forbidden' {
    const part = this.partOf(c, partId)
    if (!part?.handoffToId) return 'not_found'
    if (part.assigneeId !== this.me.id) return 'forbidden'
    part.handoffToId = null
    return this.publicCoop(c)
  }

  answerHandoff(c: StoredCoop, partId: string, accept: boolean): Schemas['Coop'] | 'not_found' {
    const part = this.partOf(c, partId)
    if (!part || part.handoffToId !== this.me.id) return 'not_found'
    part.handoffToId = null
    if (accept) {
      part.assigneeId = this.me.id
      if (part.state === 'open') this.openPart(c, part)
    }
    return this.publicCoop(c)
  }

  listCoops(): Schemas['Coop'][] {
    return this.coops
      .filter((c) => c.participants.some((p) => p.userId === this.me.id && p.status !== 'declined'))
      .map((c) => this.publicCoop(c))
      .sort((a, b) => Number(b.my_status === 'invited') - Number(a.my_status === 'invited'))
  }

  findCoop(id: string): StoredCoop | undefined {
    return this.coops.find((c) => c.id === id && c.participants.some((p) => p.userId === this.me.id))
  }

  createCoop(questId: string, friendIds: string[]): Schemas['Coop'] | 'not_found' | 'not_friends' | 'conflict' {
    const q = this.quests.find((x) => x.id === questId)
    if (!q) return 'not_found'
    if (friendIds.some((id) => !this.friends.some((f) => f.id === id))) return 'not_friends'
    if (q.state !== 'taken' || q.coop_id) return 'conflict'
    const conversation: StoredConversation = { id: uuid(), peerId: friendIds[0]!, coopId: null, createdAt: new Date().toISOString(), messages: [], lastRead: null }
    const coop: StoredCoop = {
      id: uuid(),
      title: q.title,
      category: q.category,
      duration_min: q.duration_min,
      ownerId: this.me.id,
      expiresAt: q.expires_at,
      participants: [
        { userId: this.me.id, status: 'owner', questId: q.id, completed: false },
        ...friendIds.map((userId) => ({ userId, status: 'invited' as const, questId: null, completed: false })),
      ],
      conversationId: conversation.id,
    }
    conversation.coopId = coop.id
    q.coop_id = coop.id
    this.coops.push(coop)
    this.conversations.push(conversation)
    return this.publicCoop(coop)
  }

  answerCoop(c: StoredCoop, accept: boolean): Schemas['Coop'] | 'answered' | 'limit' | 'over' {
    const me = c.participants.find((p) => p.userId === this.me.id)!
    if (me.status !== 'invited') return 'answered'
    if (!accept) {
      me.status = 'declined'
      return this.publicCoop(c)
    }
    if (Date.parse(c.expiresAt) <= Date.now()) return 'over'
    if (this.takenCount() >= MAX_TAKEN) return 'limit'
    const q: StoredQuest = {
      ...newQuest({ title: c.title, category: c.category, duration_min: c.duration_min, outdoor: false, why: null }),
      source: 'coop',
      state: 'taken',
      coop_id: c.id,
      catalogIndex: null,
    }
    this.quests.push(q)
    me.status = 'accepted'
    me.questId = q.id
    return this.publicCoop(c)
  }

  // ---- meetups from a chat (M5) ----

  suggestMeetup(c: StoredConversation): Schemas['MeetupOffer'] {
    const texts = c.messages.slice(-8).map((m) => m.text)
    const base = { starts_at: null, activity: null, venues: [], note: null, attribution: null, source: 'llm' as const }
    if (texts.length === 0) return { ...base, kind: 'unclear', note: 'Не поняла, о какой встрече речь. Напишите, где и когда хотите увидеться.' }
    const starts = new Date(Math.ceil((Date.now() + 3600_000) / 900_000) * 900_000).toISOString()
    if (texts.some((x) => /дот|игр/i.test(x))) return { ...base, kind: 'online', starts_at: starts, activity: 'Дота' }
    return {
      ...base,
      kind: 'venue',
      starts_at: starts,
      attribution: '© OpenStreetMap contributors',
      venues: sampleVenues.map((v, i) => ({
        ...v,
        id: i + 1,
        osm_url: `https://www.openstreetmap.org/node/${i + 1}`,
        gis_url: `https://2gis.ru/search/${encodeURIComponent(v.name)}`,
        yandex_url: `https://yandex.ru/maps/?text=${encodeURIComponent(v.name)}`,
      })),
    }
  }

  pickMeetup(c: StoredConversation, pick: Schemas['MeetupPick']): Schemas['Coop'] | 'invalid' | 'not_found' {
    const friends = this.chatMembers(c)
    if ((pick.venue_id == null) === (pick.activity == null) || friends.length === 0) return 'invalid'
    const venue = pick.venue_id == null ? undefined : sampleVenues[pick.venue_id - 1]
    if (pick.venue_id != null && !venue) return 'not_found'
    const conversation: StoredConversation = { id: uuid(), peerId: friends[0]!, coopId: null, createdAt: new Date().toISOString(), messages: [], lastRead: null }
    const coop: StoredCoop = {
      id: uuid(),
      title: venue ? `Встреча: ${venue.name}` : `Онлайн: ${pick.activity}`,
      category: 'social',
      duration_min: 90,
      ownerId: this.me.id,
      expiresAt: tomorrowAt4(),
      participants: [
        { userId: this.me.id, status: 'owner', questId: null, completed: false },
        ...friends.map((userId) => ({ userId, status: 'invited' as const, questId: null, completed: false })),
      ],
      conversationId: conversation.id,
      startsAt: pick.starts_at,
      ...(venue ? { place: { name: venue.name, address: venue.address, source: 'osm' } } : {}),
    }
    conversation.coopId = coop.id
    this.coops.push(coop)
    this.conversations.push(conversation)
    const mine: StoredQuest = {
      ...newQuest({ title: coop.title, category: 'social', duration_min: 90, outdoor: false, why: null }),
      source: 'coop',
      state: 'taken',
      coop_id: coop.id,
      catalogIndex: null,
    }
    this.quests.push(mine)
    coop.participants[0]!.questId = mine.id
    return this.publicCoop(coop)
  }

  private chatMembers(c: StoredConversation): string[] {
    const coop = c.coopId ? this.coops.find((x) => x.id === c.coopId) : undefined
    if (!coop) return [c.peerId]
    return coop.participants.filter((p) => p.userId !== this.me.id && (p.status === 'owner' || p.status === 'accepted')).map((p) => p.userId)
  }

  // ---- chats (US-17) ----

  private summary(id: string): Schemas['UserSummary'] {
    if (id === this.me.id) return { id, first_name: this.me.first_name, avatar_url: this.me.avatar_url ?? null }
    const f = this.friends.find((x) => x.id === id)
    return { id, first_name: f?.first_name ?? 'Удалённый пользователь', avatar_url: f?.avatar_url ?? null }
  }

  addMessage(c: StoredConversation, authorId: string, text: string, at = new Date().toISOString(), clientId: string | null = null): Schemas['Message'] {
    const message = { id: this.nextMessageId++, conversation_id: c.id, author: this.summary(authorId), text, created_at: at, client_id: clientId }
    c.messages.push(message)
    if (authorId === this.me.id) c.lastRead = message.id
    return message
  }

  conversation(c: StoredConversation): Schemas['Conversation'] {
    const peer = this.summary(c.peerId)
    const last = c.messages.at(-1) ?? null
    const coop = c.coopId ? this.coops.find((x) => x.id === c.coopId) : undefined
    const members = coop
      ? coop.participants.filter((p) => p.userId !== this.me.id && (p.status === 'owner' || p.status === 'accepted')).map((p) => this.summary(p.userId))
      : [peer]
    return {
      id: c.id,
      kind: coop ? 'coop' : 'dm',
      title: coop ? coop.title : peer.first_name,
      peer: coop ? null : peer,
      coop_id: coop?.id ?? null,
      members,
      can_send: coop ? true : this.friends.some((f) => f.id === c.peerId),
      last_message: last,
      unread_count: c.messages.filter((m) => m.id > (c.lastRead ?? 0) && m.author.id !== this.me.id).length,
      last_read_message_id: c.lastRead,
      updated_at: last?.created_at ?? c.createdAt,
    }
  }

  /** Chats the user is in: DMs, and co-op chats once owner or joined. */
  private member(c: StoredConversation): boolean {
    if (!c.coopId) return true
    const me = this.coops.find((x) => x.id === c.coopId)?.participants.find((p) => p.userId === this.me.id)
    return me?.status === 'owner' || me?.status === 'accepted'
  }

  listConversations(): Schemas['Conversation'][] {
    return this.conversations
      .filter((c) => this.member(c))
      .map((c) => this.conversation(c)).sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  }

  findConversation(id: string): StoredConversation | undefined {
    return this.conversations.find((c) => c.id === id && this.member(c))
  }

  openDirect(userId: string): Schemas['Conversation'] | 'not_friends' {
    if (!this.friends.some((f) => f.id === userId)) return 'not_friends'
    let c = this.conversations.find((x) => x.peerId === userId && !x.coopId)
    if (!c) {
      c = { id: uuid(), peerId: userId, coopId: null, createdAt: new Date().toISOString(), messages: [], lastRead: null }
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
    if (!c.coopId && !this.friends.some((f) => f.id === c.peerId)) return 'closed'
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
    // One local event takes the third catalog slot (US-19)
    const event = sampleEvents.find((e) => !this.quests.some((q) => q.event?.url === e.url))
    const catalogWanted = event && wanted >= 3 ? wanted - 1 : wanted
    for (const i of order.slice(0, Math.max(0, catalogWanted))) fresh.push({ ...newQuest(catalog[i]!), catalogIndex: i })
    if (event && catalogWanted < wanted) fresh.splice(tasks.length + 2, 0, eventQuest(event))
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
    // The last one of a co-op brings everyone +50%
    let coopBonus = 0
    const coop = q.coop_id ? this.coops.find((c) => c.id === q.coop_id) : undefined
    if (coop?.parts) {
      // The next parts open once the part they wait for is done
      const part = coop.parts.find((x) => x.questId === q.id)
      if (part) {
        part.state = 'done'
        for (const next of coop.parts) if (next.opensAfter === part.id && next.state === 'locked') this.openPart(coop, next)
      }
      const mine = coop.parts.filter((x) => x.assigneeId === this.me.id)
      coop.participants.find((p) => p.userId === this.me.id)!.completed = mine.every((x) => x.state === 'done')
    } else if (coop) {
      const joined = coop.participants.filter((p) => p.status === 'owner' || p.status === 'accepted')
      joined.find((p) => p.userId === this.me.id)!.completed = true
      if (joined.length >= 2 && joined.every((p) => p.completed)) coopBonus = Math.round(points * COOP_BONUS_SHARE)
    }
    q.points_awarded = points + coopBonus
    this.pointsToday += points + coopBonus
    this.pointsWeek += points + coopBonus
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
      coop_bonus: coopBonus,
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
    coop_id: null,
    event: null,
  }
}

function eventQuest(e: (typeof sampleEvents)[number]): StoredQuest {
  const { category, in_hours, ...info } = e
  const starts = new Date(Date.now() + in_hours * 3600_000)
  starts.setMinutes(0, 0, 0)
  return {
    ...newQuest({
      title: e.title,
      category,
      duration_min: 120,
      outdoor: false,
      why: e.is_free ? 'Бесплатно и сегодня: хороший повод выбраться.' : 'Событие сегодня в твоём городе.',
    }),
    source: 'event',
    event: { ...info, starts_at: starts.toISOString(), ends_at: new Date(starts.getTime() + 2 * 3600_000).toISOString() },
    catalogIndex: null,
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
