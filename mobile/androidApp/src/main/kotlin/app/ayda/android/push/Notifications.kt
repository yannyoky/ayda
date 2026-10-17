package app.ayda.android.push

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import app.ayda.android.BuildConfig
import app.ayda.android.MainActivity
import app.ayda.android.R
import app.ayda.shared.push.DeviceStore
import app.ayda.shared.push.PushTarget
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/** Push through Firebase Cloud Messaging (ADR 0009); off when the build has no Firebase project. */
object Push {
    const val CHANNEL = "ayda"

    val enabled: Boolean get() = BuildConfig.FIREBASE_APP_ID.isNotEmpty()

    /** Set up without google-services.json: the project comes from the build config. */
    fun init(context: Context) {
        if (!enabled) return
        if (FirebaseApp.getApps(context).isEmpty()) {
            val options =
                FirebaseOptions
                    .Builder()
                    .setApplicationId(BuildConfig.FIREBASE_APP_ID)
                    .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
                    .setApiKey(BuildConfig.FIREBASE_API_KEY)
                    .setGcmSenderId(BuildConfig.FIREBASE_SENDER_ID)
                    .build()
            FirebaseApp.initializeApp(context, options)
        }
        val channel =
            NotificationChannel(
                CHANNEL,
                context.getString(R.string.push_channel),
                NotificationManager.IMPORTANCE_DEFAULT,
            )
        context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    /** The current FCM token, or null when push is off or Google Play services are missing. */
    suspend fun token(): String? {
        if (!enabled) return null
        return suspendCancellableCoroutine { cont ->
            FirebaseMessaging
                .getInstance()
                .token
                .addOnCompleteListener { task -> cont.resume(if (task.isSuccessful) task.result else null) }
        }
    }

    /** Push data rides in the intent extras, both from the system tray and from [show]. */
    fun target(intent: Intent?): PushTarget? {
        val extras = intent?.extras ?: return null
        return PushTarget.from(extras.keySet().associateWith { extras.getString(it) })
    }

    /** A push that arrived while the app was open: the system shows nothing, so we do. */
    fun show(
        context: Context,
        title: String?,
        body: String?,
        payload: Map<String, String>,
    ) {
        val granted =
            Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
        if (!granted) return
        val open =
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .apply { payload.forEach { (key, value) -> putExtra(key, value) } }
        val tap =
            PendingIntent.getActivity(
                context,
                payload.hashCode(),
                open,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        val notification =
            NotificationCompat
                .Builder(context, CHANNEL)
                .setSmallIcon(R.drawable.ic_today)
                .setContentTitle(title ?: context.getString(R.string.app_name))
                .setContentText(body)
                .setContentIntent(tap)
                .setAutoCancel(true)
                .build()
        NotificationManagerCompat.from(context).notify(payload.hashCode(), notification)
    }
}

/** The server's id for this phone, kept in plain preferences: it is not a secret. */
class PrefsDeviceStore(
    context: Context,
) : DeviceStore {
    private val prefs = context.getSharedPreferences("push", Context.MODE_PRIVATE)

    override fun load(): String? = prefs.getString(KEY, null)

    override fun save(deviceId: String?) {
        prefs.edit { if (deviceId == null) remove(KEY) else putString(KEY, deviceId) }
    }

    private companion object {
        const val KEY = "device_id"
    }
}
