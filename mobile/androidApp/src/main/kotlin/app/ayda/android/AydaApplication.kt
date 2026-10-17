package app.ayda.android

import android.app.Application
import app.ayda.android.auth.EncryptedTokenStore
import app.ayda.android.auth.KeystoreCipher
import app.ayda.shared.AydaClient

class AydaApplication : Application() {
    val client: AydaClient by lazy {
        AydaClient(BuildConfig.API_BASE_URL, EncryptedTokenStore(filesDir.resolve("tokens.bin"), KeystoreCipher()))
    }
}
