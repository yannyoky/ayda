package app.ayda.android

import android.app.Application
import app.ayda.shared.AydaClient
import app.ayda.shared.InMemoryTokenStore

class AydaApplication : Application() {
    // Tokens move to encrypted storage together with the sign-in screen (#93).
    val client: AydaClient by lazy { AydaClient(BuildConfig.API_BASE_URL, InMemoryTokenStore()) }
}
