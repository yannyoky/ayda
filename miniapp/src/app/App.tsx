import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { AssistantScreen } from '../screens/AssistantScreen'
import { ChatScreen } from '../screens/ChatScreen'
import { ChatsScreen } from '../screens/ChatsScreen'
import { CompleteScreen } from '../screens/CompleteScreen'
import { CoopScreen } from '../screens/CoopScreen'
import { FeedScreen } from '../screens/FeedScreen'
import { FriendsScreen } from '../screens/FriendsScreen'
import { PickScreen } from '../screens/PickScreen'
import { ProfileScreen } from '../screens/ProfileScreen'
import { SignOutEverywhereScreen } from '../screens/SignOutEverywhereScreen'
import { TodayScreen } from '../screens/TodayScreen'
import { Bootstrap } from './Bootstrap'
import { launchPath } from './launch'
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
          { path: 'chats', element: <ChatsScreen /> },
          { path: 'friends', element: <FriendsScreen /> },
          { path: 'profile', element: <ProfileScreen /> },
        ],
      },
      { path: 'pick', element: <PickScreen /> },
      { path: 'assistant', element: <AssistantScreen /> },
      { path: 'quest/:id/done', element: <CompleteScreen /> },
      { path: 'chats/:id', element: <ChatScreen /> },
      { path: 'coops/:id', element: <CoopScreen /> },
      { path: 'signout', element: <SignOutEverywhereScreen /> },
    ],
    { initialEntries: [initialPath] },
  )
}

export function App({ initialPath, queryClient }: { initialPath?: string; queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? createQueryClient())
  const [router] = useState(() => createRouter(initialPath ?? launchPath()))
  return (
    <QueryClientProvider client={client}>
      <Bootstrap>
        <RouterProvider router={router} />
      </Bootstrap>
    </QueryClientProvider>
  )
}
