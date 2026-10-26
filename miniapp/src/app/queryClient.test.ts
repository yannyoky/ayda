import { ApiError } from '../api/client'
import { keys } from '../api/queries'
import { createQueryClient } from './queryClient'

const consentRequired = new ApiError(409, {
  type: 'https://ayda.app/errors/consent-required',
  title: 'Conflict',
  status: 409,
})

describe('a new consent version while the app is open', () => {
  it('reloads the profile when a query answers consent-required', async () => {
    const client = createQueryClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    await client
      .fetchQuery({ queryKey: ['feed'], queryFn: () => Promise.reject(consentRequired), retry: false })
      .catch(() => undefined)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.me })
  })

  it('reloads the profile when a mutation answers consent-required', async () => {
    const client = createQueryClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const mutation = client.getMutationCache().build(client, { mutationFn: () => Promise.reject(consentRequired) })
    await mutation.execute(undefined).catch(() => undefined)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: keys.me })
  })

  it('leaves other conflicts alone', async () => {
    const client = createQueryClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const other = new ApiError(409, { type: 'https://ayda.app/errors/coop-full', title: 'Conflict', status: 409 })
    await client.fetchQuery({ queryKey: ['coop'], queryFn: () => Promise.reject(other), retry: false }).catch(() => undefined)
    expect(invalidate).not.toHaveBeenCalled()
  })
})
