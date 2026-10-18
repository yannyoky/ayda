package app.ayda.shared.push

import app.ayda.api.models.RegisterMyDeviceRequest
import app.ayda.shared.ApiResult
import app.ayda.shared.AydaClient
import app.ayda.shared.apiCall

/** Where the app is asked to go: by a push, which carries only its `kind` and ids (ADR 0009), or by an invite link. */
sealed interface PushTarget {
    data object Today : PushTarget

    data object Feed : PushTarget

    data object Friends : PushTarget

    data class Chat(
        val conversationId: String,
    ) : PushTarget

    data class Coop(
        val coopId: String,
    ) : PushTarget

    /** A link `/i/<code>` was opened. */
    data class Invite(
        val code: String,
    ) : PushTarget

    companion object {
        /** Reads the data of a push; null for anything that is not ours. */
        fun from(data: Map<String, String?>): PushTarget? =
            when (data["kind"]) {
                "reminder.morning", "reminder.evening" -> Today
                "social.digest" -> Feed
                "ladder.weekly" -> Friends
                "chat.message" -> data["conversation_id"]?.let(::Chat)
                "coop.invite", "coop.bonus" -> data["coop_id"]?.let(::Coop)
                null -> null
                // A kind this version does not know yet: at least open the app.
                else -> Today
            }
    }
}

/** Remembers which device record the server gave this phone, to remove it on sign-out. */
interface DeviceStore {
    fun load(): String?

    fun save(deviceId: String?)
}

class InMemoryDeviceStore(
    private var id: String? = null,
) : DeviceStore {
    override fun load(): String? = id

    override fun save(deviceId: String?) {
        id = deviceId
    }
}

/** Registers the phone's FCM token with the API and removes it before signing out. */
class PushRegistration(
    private val client: AydaClient,
    private val store: DeviceStore,
    private val platform: RegisterMyDeviceRequest.Platform,
) {
    /** Idempotent per token: call on every start and whenever FCM rotates the token. */
    suspend fun register(token: String): Boolean {
        if (!client.isSignedIn()) return false
        val registered = apiCall { client.profile.registerMyDevice(RegisterMyDeviceRequest(platform, token)) }
        if (registered is ApiResult.Ok) store.save(registered.value.id)
        return registered is ApiResult.Ok
    }

    /** Stops pushes to this phone; a failure is fine, the server drops dead tokens itself. */
    suspend fun unregister() {
        val id = store.load() ?: return
        store.save(null)
        apiCall({ client.profile.removeMyDevice(id) }) {}
    }
}
