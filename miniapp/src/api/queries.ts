// TanStack Query keys and hooks over the generated client. Screens use these, not `api` directly.
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData, type QueryClient } from '@tanstack/react-query'
import { api, ApiError, setAccessToken, unwrap, type Schemas } from './client'
import { initDataRaw } from '../telegram/webapp'

export const keys = {
  session: ['session'] as const,
  me: ['me'] as const,
}

export class NotInTelegramError extends Error {
  constructor() {
    super('No Telegram initData')
    this.name = 'NotInTelegramError'
  }
}

const useMockInitData = import.meta.env.VITE_API_MOCK === '1' || import.meta.env.MODE === 'test'

/** US-01: exchange Telegram initData for an access token. */
export async function signIn(): Promise<Schemas['Session']> {
  const initData = initDataRaw() ?? (useMockInitData ? 'mock-init-data' : undefined)
  if (!initData) throw new NotInTelegramError()
  const session = await unwrap(api.POST('/auth/telegram', { body: { init_data: initData } }))
  setAccessToken(session.access_token)
  return session
}

export function useSession() {
  const client = useQueryClient()
  return useQuery({
    queryKey: keys.session,
    queryFn: async () => {
      const session = await signIn()
      client.setQueryData(keys.me, session.user)
      return session
    },
    staleTime: Infinity,
    retry: (count, error) => !(error instanceof NotInTelegramError) && !(error instanceof ApiError && error.status === 401) && count < 2,
  })
}

/** `signedIn: false` holds the request until the session exists (sign-in also fills this cache). */
export function useMe({ signedIn = true }: { signedIn?: boolean } = {}) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => unwrap(api.GET('/me')),
    enabled: signedIn,
  })
}

export function useUpdateProfile() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['ProfileUpdate']) => unwrap(api.PATCH('/me/profile', { body })),
    onMutate: async (body) => {
      await client.cancelQueries({ queryKey: keys.me })
      const previous = client.getQueryData<Schemas['Me']>(keys.me)
      if (previous && body.theme) client.setQueryData(keys.me, { ...previous, theme: body.theme })
      return { previous }
    },
    onError: (_error, _body, context) => {
      if (context?.previous) client.setQueryData(keys.me, context.previous)
    },
    onSuccess: (me) => client.setQueryData(keys.me, me),
  })
}

// ---- consent and onboarding (US-02, 152-FZ) ----

export function useAcceptConsent() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (version: string) => {
      await unwrap(api.POST('/me/consents', { body: { version } }))
      return unwrap(api.GET('/me'))
    },
    onSuccess: (me) => client.setQueryData(keys.me, me),
  })
}

export function useCompleteOnboarding() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => unwrap(api.POST('/me/onboarding/complete')),
    onSuccess: (me) => client.setQueryData(keys.me, me),
  })
}

export function useCitySearch(params: { query?: string; lat?: number; lon?: number }) {
  const enabled = (params.query?.trim().length ?? 0) >= 2 || params.lat !== undefined
  return useQuery({
    queryKey: ['cities', params],
    queryFn: () =>
      unwrap(
        api.GET('/cities', {
          params: { query: params.lat === undefined ? { query: params.query?.trim(), limit: 8 } : { lat: params.lat, lon: params.lon, limit: 8 } },
        }),
      ),
    enabled,
    staleTime: 5 * 60_000,
    placeholderData: (previous) => previous,
  })
}

export function useGoalCatalog() {
  return useQuery({ queryKey: ['goals'], queryFn: () => unwrap(api.GET('/goals')), staleTime: Infinity })
}

export function useMyGoals() {
  return useQuery({ queryKey: ['me', 'goals'], queryFn: () => unwrap(api.GET('/me/goals')) })
}

export function useSetGoals() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (goal_codes: string[]) => unwrap(api.PUT('/me/goals', { body: { goal_codes } })),
    onSuccess: (data) => client.setQueryData(['me', 'goals'], data),
  })
}

export function useMyHabits() {
  return useQuery({ queryKey: ['me', 'habits'], queryFn: () => unwrap(api.GET('/me/habits')) })
}

export function useAddHabit() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['HabitCreate']) => unwrap(api.POST('/me/habits', { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ['me', 'habits'] }),
  })
}

export function useDeleteHabit() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (habit_id: string) => unwrap(api.DELETE('/me/habits/{habit_id}', { params: { path: { habit_id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ['me', 'habits'] }),
  })
}

export function useRequestDeletion() {
  return useMutation({ mutationFn: () => unwrap(api.DELETE('/me')) })
}

// ---- day: check-in, pool, take, replace, own quests, completion (US-05..US-10) ----

export const dayKey = ['day', 'today'] as const

export function useToday() {
  return useQuery({
    queryKey: dayKey,
    queryFn: () => unwrap(api.GET('/days/today')),
    // While the assistant builds the pool, poll every 1.5 s as the contract asks
    refetchInterval: (query) => (query.state.data?.pool_status === 'generating' ? 1500 : false),
  })
}

export function useSubmitCheckin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['CheckinInput']) => unwrap(api.PUT('/days/today/checkin', { body })),
    onSuccess: (day) => {
      client.setQueryData(dayKey, day)
      // The check-in is the first message of the day chat
      void client.invalidateQueries({ queryKey: assistantKey(null) })
    },
  })
}

export function useTakeQuests() {
  const client = useQueryClient()
  return useMutation({
    // One call per quest; stops at the first failure so the limit error surfaces
    mutationFn: async (ids: string[]) => {
      for (const quest_id of ids) await unwrap(api.POST('/day-quests/{quest_id}/take', { params: { path: { quest_id } } }))
    },
    onSettled: () => client.invalidateQueries({ queryKey: dayKey }),
  })
}

export function useReplaceQuest() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: Schemas['RejectReason'] }) =>
      unwrap(api.POST('/day-quests/{quest_id}/replace', { params: { path: { quest_id: id } }, body: reason ? { reason } : {} })),
    onSuccess: (result) => {
      client.setQueryData<Schemas['Day']>(dayKey, (day) => {
        if (!day) return day
        const quests = day.quests.flatMap((q) => (q.id === result.replaced.id ? (result.replacement ? [result.replacement] : []) : [q]))
        return { ...day, quests, limits: { ...day.limits, replacements_left: result.replacements_left } }
      })
    },
    onError: () => client.invalidateQueries({ queryKey: dayKey }),
  })
}

export function useAddOwnQuest() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['OwnQuestInput']) => unwrap(api.POST('/day-quests', { body })),
    onSettled: () => client.invalidateQueries({ queryKey: dayKey }),
  })
}

export function useCompleteQuest() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Schemas['CompleteQuestInput'] }) =>
      unwrap(api.POST('/day-quests/{quest_id}/complete', { params: { path: { quest_id: id } }, body })),
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: dayKey })
      void client.invalidateQueries({ queryKey: ['feed'] })
      void client.invalidateQueries({ queryKey: ['ladder'] })
      if (result.quest.coop_id) void client.invalidateQueries({ queryKey: coopKey(result.quest.coop_id) })
    },
  })
}

// ---- social: feed, likes, comments (US-13, US-14) ----

export const feedKey = ['feed'] as const

export function useFeed() {
  return useInfiniteQuery({
    queryKey: feedKey,
    queryFn: ({ pageParam }) => unwrap(api.GET('/feed', { params: { query: { limit: 20, ...(pageParam ? { cursor: pageParam } : {}) } } })),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
}

type FeedData = InfiniteData<Schemas['PostPage'], string | null>

function patchPost(client: QueryClient, id: string, patch: (p: Schemas['Post']) => Schemas['Post'] | null) {
  client.setQueryData<FeedData>(feedKey, (data) =>
    data
      ? {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            items: page.items.flatMap((p) => {
              if (p.id !== id) return [p]
              const next = patch(p)
              return next ? [next] : []
            }),
          })),
        }
      : data,
  )
}

export function useToggleLike() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, like }: { id: string; like: boolean }) =>
      unwrap(like ? api.PUT('/posts/{post_id}/like', { params: { path: { post_id: id } } }) : api.DELETE('/posts/{post_id}/like', { params: { path: { post_id: id } } })),
    onMutate: ({ id, like }) =>
      patchPost(client, id, (p) => (p.liked_by_me === like ? p : { ...p, liked_by_me: like, like_count: p.like_count + (like ? 1 : -1) })),
    onSuccess: (state, { id }) => patchPost(client, id, (p) => ({ ...p, ...state })),
    onError: () => client.invalidateQueries({ queryKey: feedKey }),
  })
}

export function useDeletePost() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE('/posts/{post_id}', { params: { path: { post_id: id } } })),
    onSuccess: (_r, id) => patchPost(client, id, () => null),
  })
}

export function useComments(postId: string) {
  return useQuery({
    queryKey: ['comments', postId],
    queryFn: () => unwrap(api.GET('/posts/{post_id}/comments', { params: { path: { post_id: postId }, query: { limit: 50 } } })),
  })
}

export function useAddComment(postId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (text: string) => unwrap(api.POST('/posts/{post_id}/comments', { params: { path: { post_id: postId } }, body: { text } })),
    onSuccess: () => {
      patchPost(client, postId, (p) => ({ ...p, comment_count: p.comment_count + 1 }))
      return client.invalidateQueries({ queryKey: ['comments', postId] })
    },
  })
}

export function useDeleteComment(postId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (commentId: string) => unwrap(api.DELETE('/comments/{comment_id}', { params: { path: { comment_id: commentId } } })),
    onSuccess: () => {
      patchPost(client, postId, (p) => ({ ...p, comment_count: Math.max(0, p.comment_count - 1) }))
      return client.invalidateQueries({ queryKey: ['comments', postId] })
    },
  })
}

// ---- friends, invites, ladder (US-12, US-16) ----

export type LadderWeek = 'current' | 'previous'

export function useLadder(week: LadderWeek) {
  return useQuery({
    queryKey: ['ladder', week],
    queryFn: () => unwrap(api.GET('/ladder', { params: { query: { week } } })),
    placeholderData: (previous) => previous,
  })
}

export function useFriends() {
  return useQuery({ queryKey: ['friends'], queryFn: () => unwrap(api.GET('/friends')) })
}

export function useCreateInvite() {
  return useMutation({ mutationFn: () => unwrap(api.POST('/invites')) })
}

export function useRemoveFriend() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (user_id: string) => unwrap(api.DELETE('/friends/{user_id}', { params: { path: { user_id } } })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['friends'] })
      void client.invalidateQueries({ queryKey: ['ladder'] })
      void client.invalidateQueries({ queryKey: feedKey })
    },
  })
}

export function useAcceptInvite() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => unwrap(api.POST('/invites/{code}/accept', { params: { path: { code } } })),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['friends'] })
      void client.invalidateQueries({ queryKey: ['ladder'] })
      void client.invalidateQueries({ queryKey: feedKey })
    },
  })
}

// ---- chats: direct messages (US-17) ----

export const conversationsKey = ['conversations'] as const
export const conversationKey = (id: string) => ['conversation', id] as const
export const messagesKey = (id: string) => ['messages', id] as const

/** Without realtime (no token, connection down) chats fall back to polling REST. */
export function useConversations({ poll = false }: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: conversationsKey,
    queryFn: () => unwrap(api.GET('/conversations')),
    refetchInterval: poll ? 15_000 : false,
  })
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: conversationKey(id),
    queryFn: () => unwrap(api.GET('/conversations/{conversation_id}', { params: { path: { conversation_id: id } } })),
  })
}

export type MessagePages = InfiniteData<Schemas['MessagePage'], string | null>

/** Pages are newest first, as the API returns them; the screen reverses for display. */
export function useMessages(id: string, { poll = false }: { poll?: boolean } = {}) {
  return useInfiniteQuery({
    queryKey: messagesKey(id),
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/conversations/{conversation_id}/messages', {
          params: { path: { conversation_id: id }, query: { limit: 30, ...(pageParam ? { cursor: pageParam } : {}) } },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    refetchInterval: poll ? 5_000 : false,
  })
}

export function useOpenDirect() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (user_id: string) => unwrap(api.POST('/conversations/direct', { body: { user_id } })),
    onSuccess: (conversation) => {
      client.setQueryData(conversationKey(conversation.id), conversation)
      void client.invalidateQueries({ queryKey: conversationsKey })
    },
  })
}

/** Adds or replaces a message in the cached newest page (matched by id or client_id). */
export function upsertMessage(client: QueryClient, message: Schemas['Message']) {
  client.setQueryData<MessagePages>(messagesKey(message.conversation_id), (data) => {
    if (!data) return data
    const same = (m: Schemas['Message']) => m.id === message.id || (message.client_id !== null && m.client_id === message.client_id)
    const exists = data.pages.some((p) => p.items.some(same))
    const pages = data.pages.map((page, i) => {
      if (exists) return { ...page, items: page.items.map((m) => (same(m) ? message : m)) }
      return i === 0 ? { ...page, items: [message, ...page.items] } : page
    })
    if (!exists && pages.length === 0) pages.push({ items: [message], next_cursor: null })
    return { ...data, pages }
  })
}

export function removeMessage(client: QueryClient, conversationId: string, messageId: number) {
  client.setQueryData<MessagePages>(messagesKey(conversationId), (data) =>
    data ? { ...data, pages: data.pages.map((p) => ({ ...p, items: p.items.filter((m) => m.id !== messageId) })) } : data,
  )
}

export function useSendMessage(conversationId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['MessageInput']) =>
      unwrap(api.POST('/conversations/{conversation_id}/messages', { params: { path: { conversation_id: conversationId } }, body })),
    onSuccess: (message) => {
      upsertMessage(client, message)
      void client.invalidateQueries({ queryKey: conversationsKey })
    },
  })
}

export function useDeleteMessage(conversationId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (message_id: number) =>
      unwrap(api.DELETE('/conversations/{conversation_id}/messages/{message_id}', { params: { path: { conversation_id: conversationId, message_id } } })),
    onSuccess: (_r, messageId) => {
      removeMessage(client, conversationId, messageId)
      void client.invalidateQueries({ queryKey: conversationsKey })
    },
  })
}

export function useMarkRead(conversationId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (last_read_message_id: number) =>
      unwrap(api.POST('/conversations/{conversation_id}/read', { params: { path: { conversation_id: conversationId } }, body: { last_read_message_id } })),
    onMutate: (lastRead) => {
      client.setQueryData<{ items: Schemas['Conversation'][] }>(conversationsKey, (data) =>
        data ? { items: data.items.map((c) => (c.id === conversationId ? { ...c, unread_count: 0, last_read_message_id: Math.max(lastRead, c.last_read_message_id ?? 0) } : c)) } : data,
      )
    },
  })
}

// ---- co-op quests (US-18) ----

export const coopsKey = ['coops'] as const
export const coopKey = (id: string) => ['coop', id] as const

export function useCoops() {
  return useQuery({ queryKey: coopsKey, queryFn: () => unwrap(api.GET('/coops')) })
}

export function useCoop(id: string) {
  return useQuery({
    queryKey: coopKey(id),
    queryFn: () => unwrap(api.GET('/coops/{coop_id}', { params: { path: { coop_id: id } } })),
  })
}

function storeCoop(client: QueryClient, coop: Schemas['Coop']) {
  client.setQueryData(coopKey(coop.id), coop)
  void client.invalidateQueries({ queryKey: coopsKey })
  void client.invalidateQueries({ queryKey: dayKey })
  void client.invalidateQueries({ queryKey: conversationsKey })
}

export function useCreateCoop() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ questId, friendIds }: { questId: string; friendIds: string[] }) =>
      unwrap(api.POST('/day-quests/{quest_id}/coop', { params: { path: { quest_id: questId } }, body: { friend_ids: friendIds } })),
    onSuccess: (coop) => storeCoop(client, coop),
  })
}

export function useAnswerCoop() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, accept }: { id: string; accept: boolean }) =>
      accept
        ? unwrap(api.POST('/coops/{coop_id}/accept', { params: { path: { coop_id: id } } }))
        : unwrap(api.POST('/coops/{coop_id}/decline', { params: { path: { coop_id: id } } })),
    onSuccess: (coop) => storeCoop(client, coop),
    onError: () => client.invalidateQueries({ queryKey: coopsKey }),
  })
}

// ---- parts of a shared plan (M5, ADR 0010) ----

type PartPath = { coopId: string; partId: string }
const partPath = ({ coopId, partId }: PartPath) => ({ coop_id: coopId, part_id: partId })

export function useSetCoopItem() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, done, ...path }: PartPath & { itemId: string; done: boolean }) =>
      unwrap(api.PATCH('/coops/{coop_id}/parts/{part_id}/items/{item_id}', { params: { path: { ...partPath(path), item_id: itemId } }, body: { done } })),
    onSuccess: (coop) => storeCoop(client, coop),
    onError: (_error, { coopId }) => client.invalidateQueries({ queryKey: coopKey(coopId) }),
  })
}

export function useOfferHandoff() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ friendId, ...path }: PartPath & { friendId: string }) =>
      unwrap(api.POST('/coops/{coop_id}/parts/{part_id}/handoff', { params: { path: partPath(path) }, body: { friend_id: friendId } })),
    onSuccess: (coop) => storeCoop(client, coop),
    onError: (_error, { coopId }) => client.invalidateQueries({ queryKey: coopKey(coopId) }),
  })
}

export function useWithdrawHandoff() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (path: PartPath) => unwrap(api.DELETE('/coops/{coop_id}/parts/{part_id}/handoff', { params: { path: partPath(path) } })),
    onSuccess: (coop) => storeCoop(client, coop),
    onError: (_error, { coopId }) => client.invalidateQueries({ queryKey: coopKey(coopId) }),
  })
}

export function useAnswerHandoff() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ accept, ...path }: PartPath & { accept: boolean }) =>
      accept
        ? unwrap(api.POST('/coops/{coop_id}/parts/{part_id}/handoff/accept', { params: { path: partPath(path) } }))
        : unwrap(api.POST('/coops/{coop_id}/parts/{part_id}/handoff/decline', { params: { path: partPath(path) } })),
    onSuccess: (coop) => storeCoop(client, coop),
    onError: (_error, { coopId }) => client.invalidateQueries({ queryKey: coopKey(coopId) }),
  })
}

// ---- meetup from a chat (M5) ----

export function useSuggestMeetup(conversationId: string) {
  return useMutation({
    mutationFn: () => unwrap(api.POST('/conversations/{conversation_id}/meetup', { params: { path: { conversation_id: conversationId } } })),
  })
}

export function usePickMeetup(conversationId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['MeetupPick']) =>
      unwrap(api.POST('/conversations/{conversation_id}/meetup/pick', { params: { path: { conversation_id: conversationId } }, body })),
    onSuccess: (coop) => storeCoop(client, coop),
  })
}

// ---- cooking quests (M5, ADR 0012) ----

export function useSuggestRecipes() {
  return useMutation({ mutationFn: (body: Schemas['RecipeSuggestInput']) => unwrap(api.POST('/recipes/suggest', { body })) })
}

export function useRecipe(id: string | null, servings: number) {
  return useQuery({
    queryKey: ['recipe', id, servings],
    enabled: id !== null,
    queryFn: () => unwrap(api.GET('/recipes/{recipe_id}', { params: { path: { recipe_id: id ?? '' }, query: { servings } } })),
  })
}

export function usePlanRecipe() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ recipeId, ...body }: Schemas['RecipePlanInput'] & { recipeId: string }) =>
      unwrap(api.POST('/recipes/{recipe_id}/plan', { params: { path: { recipe_id: recipeId } }, body })),
    onSuccess: (coop) => storeCoop(client, coop),
  })
}

// ---- assistant chat: the day topic and one topic per quest (ADR 0013) ----

export const assistantKey = (questId: string | null) => ['assistant', questId ?? 'day'] as const

export function useAssistantThread(questId: string | null) {
  return useQuery({
    queryKey: assistantKey(questId),
    queryFn: () => unwrap(api.GET('/assistant/messages', { params: { query: questId ? { quest_id: questId } : {} } })),
  })
}

export function useSendAssistantMessage(questId: string | null) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (text: string) => unwrap(api.POST('/assistant/messages', { body: questId ? { text, quest_id: questId } : { text } })),
    onSuccess: (exchange) => {
      client.setQueryData<Schemas['AssistantThread']>(assistantKey(questId), (thread) => ({
        items: [...(thread?.items ?? []), exchange.sent, exchange.reply],
        messages_left: exchange.messages_left,
      }))
      // A suggested quest lands in today's pool
      if (exchange.reply.cards.some((c) => c.quest)) void client.invalidateQueries({ queryKey: dayKey })
    },
  })
}
