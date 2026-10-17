package app.ayda.shared.realtime

import io.github.centrifugal.centrifuge.Client
import io.github.centrifugal.centrifuge.ConnectedEvent
import io.github.centrifugal.centrifuge.ConnectingEvent
import io.github.centrifugal.centrifuge.ConnectionTokenEvent
import io.github.centrifugal.centrifuge.ConnectionTokenGetter
import io.github.centrifugal.centrifuge.DisconnectedEvent
import io.github.centrifugal.centrifuge.EventListener
import io.github.centrifugal.centrifuge.Options
import io.github.centrifugal.centrifuge.PublicationEvent
import io.github.centrifugal.centrifuge.SubscribedEvent
import io.github.centrifugal.centrifuge.Subscription
import io.github.centrifugal.centrifuge.SubscriptionEventListener
import io.github.centrifugal.centrifuge.TokenCallback

/** Centrifugo over centrifuge-java (protobuf protocol, its own reconnects and recovery). */
class CentrifugeTransport : RealtimeTransport {
    override fun open(
        url: String,
        channel: String,
        token: String,
        tokens: TokenSource,
        listener: RealtimeListener,
    ): RealtimeConnection {
        val options =
            Options().apply {
                setToken(token)
                tokenGetter =
                    object : ConnectionTokenGetter() {
                        override fun getConnectionToken(
                            event: ConnectionTokenEvent,
                            cb: TokenCallback,
                        ) = tokens.fetch { result ->
                            when (result) {
                                is TokenResult.Ok -> cb.Done(null, result.token)
                                // An empty token tells the SDK the user is not allowed to connect any more.
                                TokenResult.Unauthorized -> cb.Done(null, "")
                                is TokenResult.Failed -> cb.Done(result.cause, null)
                            }
                        }
                    }
            }
        val client =
            Client(
                url,
                options,
                object : EventListener() {
                    override fun onConnecting(
                        client: Client,
                        event: ConnectingEvent,
                    ) = listener.onStatus(RealtimeStatus.Connecting)

                    override fun onConnected(
                        client: Client,
                        event: ConnectedEvent,
                    ) = listener.onStatus(RealtimeStatus.Live)

                    override fun onDisconnected(
                        client: Client,
                        event: DisconnectedEvent,
                    ) = listener.onStatus(RealtimeStatus.Off)
                },
            )
        val subscription =
            client.newSubscription(
                channel,
                object : SubscriptionEventListener() {
                    override fun onPublication(
                        sub: Subscription,
                        event: PublicationEvent,
                    ) = listener.onPublication(event.data.decodeToString())

                    override fun onSubscribed(
                        sub: Subscription,
                        event: SubscribedEvent,
                    ) {
                        if (event.wasRecovering() == true) listener.onResubscribed(recovered = event.recovered == true)
                    }
                },
            )
        subscription.subscribe()
        client.connect()
        return object : RealtimeConnection {
            override fun pause() = client.disconnect()

            override fun resume() = client.connect()

            override fun close() {
                client.disconnect()
                // Frees the SDK's threads without blocking the caller.
                Thread { client.close(CLOSE_WAIT_MS) }.start()
            }
        }
    }

    private companion object {
        const val CLOSE_WAIT_MS = 5_000L
    }
}
