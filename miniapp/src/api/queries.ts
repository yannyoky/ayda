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

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => unwrap(api.GET('/me')),
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
    onSuccess: (day) => client.setQueryData(dayKey, day),
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
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: dayKey })
      void client.invalidateQueries({ queryKey: ['feed'] })
      void client.invalidateQueries({ queryKey: ['ladder'] })
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
