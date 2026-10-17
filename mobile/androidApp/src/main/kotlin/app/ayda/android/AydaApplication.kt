package app.ayda.android

import android.app.Application
import app.ayda.android.auth.EncryptedTokenStore
import app.ayda.android.auth.KeystoreCipher
import app.ayda.android.push.PrefsDeviceStore
import app.ayda.android.push.Push
import app.ayda.api.models.RegisterMyDeviceRequest
import app.ayda.shared.AydaClient
import app.ayda.shared.push.PushRegistration
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class AydaApplication : Application() {
    /** For work that outlives a screen, such as registering a new push token. */
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val client: AydaClient by lazy {
        AydaClient(BuildConfig.API_BASE_URL, EncryptedTokenStore(filesDir.resolve("tokens.bin"), KeystoreCipher()))
    }

    val push: PushRegistration by lazy {
        PushRegistration(client, PrefsDeviceStore(this), RegisterMyDeviceRequest.Platform.android)
    }

    override fun onCreate() {
        super.onCreate()
        Push.init(this)
    }
}
