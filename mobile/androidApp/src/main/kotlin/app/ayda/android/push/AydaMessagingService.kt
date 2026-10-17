package app.ayda.android.push

import app.ayda.android.AydaApplication
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.launch

class AydaMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        val app = application as AydaApplication
        app.scope.launch { app.push.register(token) }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val notification = message.notification
        Push.show(this, notification?.title, notification?.body, message.data)
    }
}
