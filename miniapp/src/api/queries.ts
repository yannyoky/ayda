// TanStack Query keys and hooks over the generated client. Screens use these, not `api` directly.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
