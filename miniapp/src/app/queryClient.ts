import { QueryCache, QueryClient } from '@tanstack/react-query'
import { ApiError, setAccessToken } from '../api/client'
import { keys } from '../api/queries'

export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        // An expired token: sign in again with the same initData
        if (error instanceof ApiError && error.status === 401 && query.queryKey[0] !== keys.session[0]) {
          setAccessToken(undefined)
          void client.resetQueries({ queryKey: keys.session })
        }
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      },
    },
  })
  return client
}
