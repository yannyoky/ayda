import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { CompleteScreen } from '../screens/CompleteScreen'
import { FeedScreen } from '../screens/FeedScreen'
import { FriendsScreen } from '../screens/FriendsScreen'
import { PickScreen } from '../screens/PickScreen'
import { ProfileScreen } from '../screens/ProfileScreen'
import { TodayScreen } from '../screens/TodayScreen'
import { Bootstrap } from './Bootstrap'
import { createQueryClient } from './queryClient'
import { Shell } from './Shell'

// Memory routing: Telegram passes launch params in the URL hash, so the app does not own the URL
function createRouter(initialPath: string) {
  return createMemoryRouter(
    [
      {
        element: <Shell />,
        children: [
          { index: true, element: <TodayScreen /> },
          { path: 'feed', element: <FeedScreen /> },
          { path: 'friends', element: <FriendsScreen /> },
          { path: 'profile', element: <ProfileScreen /> },
        ],
      },
      { path: 'pick', element: <PickScreen /> },
      { path: 'quest/:id/done', element: <CompleteScreen /> },
    ],
    { initialEntries: [initialPath] },
  )
}

export function App({ initialPath = '/', queryClient }: { initialPath?: string; queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? createQueryClient())
  const [router] = useState(() => createRouter(initialPath))
  return (
    <QueryClientProvider client={client}>
      <Bootstrap>
        <RouterProvider router={router} />
      </Bootstrap>
    </QueryClientProvider>
  )
}
