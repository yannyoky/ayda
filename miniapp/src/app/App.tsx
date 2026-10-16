import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { FeedScreen } from '../screens/FeedScreen'
import { FriendsScreen } from '../screens/FriendsScreen'
import { ProfileScreen } from '../screens/ProfileScreen'
import { TodayScreen } from '../screens/TodayScreen'
import { Shell } from './Shell'
import { createQueryClient } from './queryClient'
import { ThemeProvider } from './ThemeProvider'

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
    ],
    { initialEntries: [initialPath] },
  )
}

export function App({ initialPath = '/', queryClient }: { initialPath?: string; queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? createQueryClient())
  const [router] = useState(() => createRouter(initialPath))
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <RouterProvider router={router} />
      </ThemeProvider>
    </QueryClientProvider>
  )
}
