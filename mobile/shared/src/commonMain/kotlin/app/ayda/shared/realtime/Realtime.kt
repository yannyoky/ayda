package app.ayda.shared.realtime

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.ayda.api.models.ConversationReadEvent
import app.ayda.api.models.CoopUpdatedEvent
import app.ayda.api.models.Message
import app.ayda.api.models.MessageCreatedEvent
import app.ayda.api.models.MessageDeletedEvent
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.time.Duration

enum class RealtimeStatus { Off, Connecting, Live }

/** One event from the user's personal channel (`RealtimeEvent` in the contract, ADR 0007). */
sealed interface LiveEvent {
    data class MessageCreated(
        val message: Message,
    ) : LiveEvent

    data class MessageDeleted(
        val conversationId: String,
        val messageId: Long,
    ) : LiveEvent

    data class ConversationRead(
        val conversationId: String,
        val userId: String,
        val lastReadMessageId: Long,
    ) : LiveEvent

    data class CoopUpdated(
        val coopId: String,
    ) : LiveEvent

    /** Events were missed and could not be recovered: reload everything over REST. */
    data object Resync : LiveEvent
}

sealed interface TokenResult {
    data class Ok(
        val token: String,
    ) : TokenResult

    /** The session is gone: the SDK stops reconnecting. */
    data object Unauthorized : TokenResult

    /** No answer: the SDK retries later. */
    data class Failed(
        val cause: Throwable,
    ) : TokenResult
}

/** Gives the SDK a fresh connection token when the current one is about to expire. */
fun interface TokenSource {
    fun fetch(done: (TokenResult) -> Unit)
}

/** Callbacks from the SDK; they may come on any thread. */
interface RealtimeListener {
    fun onStatus(status: RealtimeStatus)

    /** The raw JSON of one publication. */
    fun onPublication(data: String)

    /** Subscribed again after a drop; [recovered] is false when publications were lost. */
    fun onResubscribed(recovered: Boolean)
}

interface RealtimeConnection {
    /** Disconnects but keeps the stream position, so [resume] recovers what was missed. */
    fun pause()

    fun resume()

    fun close()
}

/**
 * A platform Centrifugo SDK behind one interface (ADR 0009): centrifuge-java on Android,
 * centrifuge-swift on iOS. It connects, subscribes to [channel] with recovery and reconnects.
 */
fun interface RealtimeTransport {
    fun open(
        url: String,
        channel: String,
        token: String,
        tokens: TokenSource,
        listener: RealtimeListener,
    ): RealtimeConnection
}

/**
 * The signed-in user's live connection (ADR 0007). Screens collect [events] and, while
 * [live] is false, poll REST instead. The app pauses it in the background.
 */
class Realtime(
    private val client: AydaClient,
    private val transport: RealtimeTransport,
) : ViewModel() {
    private val mutableStatus = MutableStateFlow(RealtimeStatus.Off)
    val status: StateFlow<RealtimeStatus> = mutableStatus.asStateFlow()

    private val mutableForeground = MutableStateFlow(true)

    /** False while the app is in the background: screens stop polling too. */
    val foreground: StateFlow<Boolean> = mutableForeground.asStateFlow()

    private val mutableEvents = MutableSharedFlow<LiveEvent>(extraBufferCapacity = 64)
    val events: SharedFlow<LiveEvent> = mutableEvents.asSharedFlow()

    val live: Boolean get() = status.value == RealtimeStatus.Live

    private var connection: RealtimeConnection? = null
    private var starting: Job? = null

    private val listener =
        object : RealtimeListener {
            override fun onStatus(status: RealtimeStatus) {
                mutableStatus.value = status
            }

            override fun onPublication(data: String) {
                decodeEvent(data)?.let { mutableEvents.tryEmit(it) }
            }

            override fun onResubscribed(recovered: Boolean) {
                if (!recovered) mutableEvents.tryEmit(LiveEvent.Resync)
            }
        }

    private val tokens =
        TokenSource { done ->
            viewModelScope.launch {
                done(
                    when (val fresh = apiCall { client.chat.getRealtimeToken() }) {
                        is ApiResult.Ok -> TokenResult.Ok(fresh.value.token)
                        is ApiResult.Failed ->
                            if (fresh.problem.status ==
                                401
                            ) {
                                TokenResult.Unauthorized
                            } else {
                                TokenResult.Failed(IllegalStateException())
                            }
                        is ApiResult.Offline -> TokenResult.Failed(fresh.cause)
                    },
                )
            }
        }

    init {
        start()
    }

    /** The app came to the foreground. */
    fun resume() {
        if (mutableForeground.value) return
        mutableForeground.value = true
        connection?.resume() ?: start()
    }

    /** The app went to the background. */
    fun pause() {
        if (!mutableForeground.value) return
        mutableForeground.value = false
        connection?.pause()
        if (connection == null) starting?.cancel()
        mutableStatus.value = RealtimeStatus.Off
    }

    private fun start() {
        if (connection != null || starting?.isActive == true) return
        mutableStatus.value = RealtimeStatus.Connecting
        starting =
            viewModelScope.launch {
                when (val token = apiCall { client.chat.getRealtimeToken() }) {
                    is ApiResult.Ok -> {
                        val t = token.value
                        connection = transport.open(t.url, t.channel, t.token, tokens, listener)
                    }
                    // No realtime on this server (503) or no network: screens poll, the next resume retries.
                    else -> mutableStatus.value = RealtimeStatus.Off
                }
            }
    }

    override fun onCleared() {
        connection?.close()
        connection = null
    }

    companion object {
        /** Unknown types and broken payloads are ignored. */
        fun decodeEvent(data: String): LiveEvent? =
            runCatching {
                val json = AydaClient.ApiJson
                val obj: JsonObject = json.parseToJsonElement(data).jsonObject
                when (obj["type"]?.jsonPrimitive?.content) {
                    "message.created" ->
                        LiveEvent.MessageCreated(
                            json.decodeFromJsonElement(MessageCreatedEvent.serializer(), obj).message,
                        )
                    "message.deleted" ->
                        json.decodeFromJsonElement(MessageDeletedEvent.serializer(), obj).let {
                            LiveEvent.MessageDeleted(it.conversationId, it.messageId)
                        }
                    "conversation.read" ->
                        json.decodeFromJsonElement(ConversationReadEvent.serializer(), obj).let {
                            LiveEvent.ConversationRead(it.conversationId, it.userId, it.lastReadMessageId)
                        }
                    "coop.updated" ->
                        LiveEvent.CoopUpdated(
                            json.decodeFromJsonElement(CoopUpdatedEvent.serializer(), obj).coopId,
                        )
                    else -> null
                }
            }.getOrNull()
    }
}

/** Runs [block] every [period] while the app is in the foreground and realtime is down. */
fun CoroutineScope.pollWhileOffline(
    realtime: Realtime,
    period: Duration,
    block: suspend () -> Unit,
): Job =
    launch {
        combine(realtime.foreground, realtime.status) { foreground, status ->
            foreground &&
                status != RealtimeStatus.Live
        }.distinctUntilChanged()
            .collectLatest { needed ->
                while (needed) {
                    delay(period)
                    block()
                }
            }
    }
