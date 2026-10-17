package app.ayda.shared.realtime

internal const val TOKEN_JSON =
    """{"token":"t1","expires_at":"2026-10-17T21:00:00Z","url":"wss://api.test/connection/websocket",""" +
        """"channel":"personal:#me"}"""

/** Stands in for the Centrifugo SDK: the test drives the status and the publications. */
internal class FakeTransport(
    private val connectLive: Boolean = true,
) : RealtimeTransport {
    var opened: Pair<String, String>? = null
    var listener: RealtimeListener? = null
    var tokens: TokenSource? = null
    val calls = mutableListOf<String>()

    override fun open(
        url: String,
        channel: String,
        token: String,
        tokens: TokenSource,
        listener: RealtimeListener,
    ): RealtimeConnection {
        opened = url to channel
        this.listener = listener
        this.tokens = tokens
        if (connectLive) listener.onStatus(RealtimeStatus.Live)
        return object : RealtimeConnection {
            override fun pause() {
                calls += "pause"
            }

            override fun resume() {
                calls += "resume"
            }

            override fun close() {
                calls += "close"
            }
        }
    }

    fun publish(json: String) = listener!!.onPublication(json)
}
