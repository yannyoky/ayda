package app.ayda.android

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import app.ayda.android.push.Push
import app.ayda.android.ui.AydaApp
import app.ayda.shared.push.PushTarget
import kotlinx.coroutines.flow.MutableStateFlow

class MainActivity : ComponentActivity() {
    /** The screen a tapped push asks for; the app clears it once it got there. */
    private val opened = MutableStateFlow<PushTarget?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (savedInstanceState == null) opened.value = Push.target(intent)
        val app = application as AydaApplication
        setContent { AydaApp(app.client, app.push, opened, onOpened = { opened.value = null }) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        Push.target(intent)?.let { opened.value = it }
    }
}
