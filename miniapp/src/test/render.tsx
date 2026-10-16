import { render } from '@testing-library/react'
import { App } from '../app/App'
import { createQueryClient } from '../app/queryClient'

/** Renders the whole app against the mock API, signed in through the mock Telegram flow. */
export function renderApp(initialPath = '/') {
  const queryClient = createQueryClient()
  return { queryClient, ...render(<App initialPath={initialPath} queryClient={queryClient} />) }
}
