// Live chat and co-op updates over Centrifugo (ADR 0007): one personal channel per user. REST stays the
// source of truth, so any gap (no token, a long disconnect) is closed by refetching queries.
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import type { Centrifuge } from 'centrifuge'
import { useEffect, useSyncExternalStore } from 'react'
import { api, unwrap, type Schemas } from '../api/client'
import { conversationKey, conversationsKey, coopKey, coopsKey, dayKey, removeMessage, upsertMessage } from '../api/queries'

export type RealtimeStatus = 'off' | 'connecting' | 'live'

let status: RealtimeStatus = 'off'
const listeners = new Set<() => void>()

function setStatus(next: RealtimeStatus) {
  if (next === status) return
  status = next
  listeners.forEach((l) => l())
}

export function useRealtimeStatus(): RealtimeStatus {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => status,
  )
}

type RealtimeEvent = Schemas['RealtimeEvent'] | { type: string }

/** Applies one event from the personal channel to the query cache. Unknown types are ignored. */
export function handleRealtimeEvent(client: QueryClient, event: RealtimeEvent): void {
  switch (event.type) {
    case 'message.created': {
      const { message } = event as Schemas['MessageCreatedEvent']
      upsertMessage(client, message)
      void client.invalidateQueries({ queryKey: conversationsKey })
      void client.invalidateQueries({ queryKey: conversationKey(message.conversation_id) })
      return
    }
    case 'message.updated': {
      const { message } = event as Schemas['MessageUpdatedEvent']
      upsertMessage(client, message)
      void client.invalidateQueries({ queryKey: conversationsKey })
      return
    }
    case 'message.deleted': {
      const e = event as Schemas['MessageDeletedEvent']
      removeMessage(client, e.conversation_id, e.message_id)
      void client.invalidateQueries({ queryKey: conversationsKey })
      return
    }
    case 'conversation.read': {
      const e = event as Schemas['ConversationReadEvent']
      void client.invalidateQueries({ queryKey: conversationsKey })
      void client.invalidateQueries({ queryKey: conversationKey(e.conversation_id) })
      return
    }
    case 'coop.updated': {
      const e = event as Schemas['CoopUpdatedEvent']
      void client.invalidateQueries({ queryKey: coopsKey })
      void client.invalidateQueries({ queryKey: coopKey(e.coop_id) })
      void client.invalidateQueries({ queryKey: dayKey })
      void client.invalidateQueries({ queryKey: conversationsKey })
      return
    }
    default:
      return
  }
}

/** Events were missed and could not be recovered: reload everything they could change. */
export function resync(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: coopsKey })
  void client.invalidateQueries({ queryKey: ['coop'] })
  void client.invalidateQueries({ queryKey: conversationsKey })
  void client.invalidateQueries({ queryKey: ['conversation'] })
  void client.invalidateQueries({ queryKey: ['messages'] })
}

async function fetchToken(): Promise<Schemas['RealtimeToken']> {
  return unwrap(api.POST('/realtime/token'))
}

/** Connects for the signed-in user; returns a function that disconnects. */
export function startRealtime(client: QueryClient): () => void {
  let centrifuge: Centrifuge | undefined
  let stopped = false
  setStatus('connecting')
  void Promise.all([fetchToken(), import('centrifuge')])
    .then(([token, { Centrifuge }]) => {
      if (stopped) return
      centrifuge = new Centrifuge(token.url, {
        token: token.token,
        getToken: async () => (await fetchToken()).token,
      })
      centrifuge.on('connecting', () => setStatus('connecting'))
      centrifuge.on('connected', () => setStatus('live'))
      centrifuge.on('disconnected', () => setStatus('off'))
      const sub = centrifuge.newSubscription(token.channel)
      sub.on('publication', (ctx) => handleRealtimeEvent(client, ctx.data as RealtimeEvent))
      sub.on('subscribed', (ctx) => {
        if (ctx.wasRecovering && !ctx.recovered) resync(client)
      })
      sub.subscribe()
      centrifuge.connect()
    })
    // No realtime on this server (503) or no network: screens poll instead
    .catch(() => setStatus('off'))
  return () => {
    stopped = true
    centrifuge?.disconnect()
    setStatus('off')
  }
}

export function useRealtime(enabled: boolean): void {
  const client = useQueryClient()
  useEffect(() => (enabled ? startRealtime(client) : undefined), [client, enabled])
}

