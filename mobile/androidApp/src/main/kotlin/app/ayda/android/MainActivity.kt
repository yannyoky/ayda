package app.ayda.android

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import app.ayda.android.push.Push
import app.ayda.android.ui.AydaApp
import app.ayda.shared.push.PushTarget
import app.ayda.shared.social.InviteLink
import kotlinx.coroutines.flow.MutableStateFlow

class MainActivity : ComponentActivity() {
    /** The screen a tapped push asks for; the app clears it once it got there. */
    private val opened = MutableStateFlow<PushTarget?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (savedInstanceState == null) opened.value = target(intent)
        val app = application as AydaApplication
        setContent { AydaApp(app.client, app.push, opened, onOpened = { opened.value = null }) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        target(intent)?.let { opened.value = it }
    }

    /** An invite link of our own host, else the screen a push asks for. */
    private fun target(intent: Intent): PushTarget? {
        val link = intent.data?.takeIf { it.scheme == "https" && it.host == BuildConfig.INVITE_HOST }
        return InviteLink.codeFrom(link?.path)?.let(PushTarget::Invite) ?: Push.target(intent)
    }
}
